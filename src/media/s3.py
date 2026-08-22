from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from time import monotonic
from typing import Any
from urllib.parse import quote

from aiobotocore.session import get_session
from botocore.config import Config

from media.errors import (
    MEDIA_DRAIN_TIMEOUT,
    MEDIA_MULTIPART_ETAG_MISSING,
    MEDIA_MULTIPART_ID_MISSING,
    MEDIA_STORAGE_CLOSED,
    StorageError,
)
from media.model import (
    MultipartUploadHandle,
    MultipartUploadPart,
    StorageHealth,
    StorageResult,
    StorageStatus,
)

MIN_MULTIPART_PART_SIZE = 5 * 1024 * 1024
DEFAULT_MULTIPART_PART_SIZE = 8 * 1024 * 1024
DEFAULT_LINK_TTL = 3600
CACHE_CONTROL_IMMUTABLE = "public, max-age=31536000, immutable"
_STREAM_CHUNK_SIZE = 1024 * 1024


class S3StorageService:
    """S3/MinIO-compatible storage backed by aiobotocore.

    Mirrors the behaviour of the TS ``MinioStorageService``:
    - every operation is wrapped into a ``StorageError`` with a ``MEDIA_*_FAILED`` code,
    - closed/immutable life-cycle states reject new operations,
    - ``drain``/``close``/``shutdown`` coordinate graceful shutdown.
    """

    def __init__(  # noqa: PLR0913
        self,
        endpoint: str = "http://localhost:9000",
        region: str = "us-east-1",
        access_key_id: str = "minioadmin",
        secret_access_key: str = "minioadmin",
        bucket: str = "omnixys",
        *,
        force_path_style: bool = True,
        link_ttl: int = DEFAULT_LINK_TTL,
        public_url: str = "",
    ) -> None:
        _validate_options(
            endpoint=endpoint,
            region=region,
            bucket=bucket,
            link_ttl=link_ttl,
        )
        self._endpoint = endpoint
        self._region = region
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._bucket = bucket
        self._force_path_style = force_path_style
        self._link_ttl = link_ttl
        self._public_url = public_url
        self._session = get_session()
        self._active_operations = 0
        self._operation_depth = 0
        self._closing = False
        self._closed = False
        self._drain_waiters: set[asyncio.Future[None]] = set()

    async def _s3_client(self) -> Any:
        s3_config = Config(
            s3={"addressing_style": "path" if self._force_path_style else "virtual"},
        )
        client = await self._session.create_client(
            "s3",
            region_name=self._region,
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key_id,
            aws_secret_access_key=self._secret_access_key,
            use_ssl=self._endpoint.startswith("https"),
            config=s3_config,
        )
        return await client.__aenter__()

    @staticmethod
    async def _close_client(client: Any) -> None:
        await client.__aexit__(None, None, None)

    async def _operate(self, operation: str, key: str, task: Callable[[], Awaitable[Any]]) -> Any:
        if self._closed or (self._closing and self._operation_depth == 0):
            raise StorageError(
                "Storage client is not accepting operations",
                code=MEDIA_STORAGE_CLOSED,
                metadata={"operation": operation},
            )
        self._active_operations += 1
        self._operation_depth += 1
        try:
            return await task()
        except StorageError:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            code = f"MEDIA_{operation.upper()}_FAILED"
            raise StorageError(
                "Storage operation failed",
                code=code,
                metadata={"operation": operation, "key": key},
            ) from exc
        finally:
            self._operation_depth -= 1
            self._active_operations -= 1
            if self._active_operations == 0:
                self._notify_drain_waiters()

    def _notify_drain_waiters(self) -> None:
        for waiter in self._drain_waiters:
            if not waiter.done():
                waiter.set_result(None)
        self._drain_waiters.clear()

    async def _presigned_put(self, client: Any, key: str, mimetype: str, ttl: int | None) -> str:
        return str(
            client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": key,
                    "ContentType": mimetype,
                },
                ExpiresIn=ttl or self._link_ttl,
            ),
        )

    async def _presigned_get(self, client: Any, key: str, ttl: int | None) -> str:
        return str(
            client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": key,
                },
                ExpiresIn=ttl or self._link_ttl,
            ),
        )

    async def upload(self, key: str, data: bytes, mimetype: str) -> StorageResult:
        client = await self._s3_client()
        try:
            resp = await self._operate(
                "upload",
                key,
                lambda: client.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=data,
                    ContentType=mimetype,
                    CacheControl=CACHE_CONTROL_IMMUTABLE,
                ),
            )
        finally:
            await self._close_client(client)
        return StorageResult(
            key=key,
            etag=resp.get("ETag", ""),
            version_id=resp.get("VersionId"),
            public_url=self.get_public_url(key),
        )

    async def upload_stream(self, key: str, stream: AsyncIterator[bytes], mimetype: str) -> StorageResult:
        try:
            chunks = [chunk async for chunk in stream]
        except Exception as exc:
            raise StorageError(
                "Storage operation failed",
                code="MEDIA_UPLOAD_STREAM_FAILED",
                metadata={"operation": "upload_stream", "key": key},
            ) from exc
        return await self.upload(key=key, data=b"".join(chunks), mimetype=mimetype)

    async def create_multipart_upload(self, key: str, mimetype: str) -> MultipartUploadHandle:
        client = await self._s3_client()
        try:
            resp = await self._operate(
                "multipart_create",
                key,
                lambda: client.create_multipart_upload(
                    Bucket=self._bucket,
                    Key=key,
                    ContentType=mimetype,
                ),
            )
        finally:
            await self._close_client(client)
        upload_id = resp.get("UploadId")
        if not upload_id:
            raise StorageError(
                "Storage provider did not return a multipart upload ID",
                code=MEDIA_MULTIPART_ID_MISSING,
                metadata={"key": key},
            )
        return MultipartUploadHandle(key=key, upload_id=upload_id)

    async def upload_part(
        self,
        handle: MultipartUploadHandle,
        *,
        part_number: int,
        body: bytes,
    ) -> MultipartUploadPart:
        if not isinstance(part_number, int) or isinstance(part_number, bool) or part_number < 1:
            raise ValueError("Multipart partNumber must be a positive integer")
        client = await self._s3_client()
        try:
            resp = await self._operate(
                "multipart_part",
                handle.key,
                lambda: client.upload_part(
                    Bucket=self._bucket,
                    Key=handle.key,
                    UploadId=handle.upload_id,
                    PartNumber=part_number,
                    Body=body,
                ),
            )
        finally:
            await self._close_client(client)
        etag = resp.get("ETag")
        if not etag:
            raise StorageError(
                "Storage provider did not return a multipart ETag",
                code=MEDIA_MULTIPART_ETAG_MISSING,
                metadata={"key": handle.key, "part_number": part_number},
            )
        return MultipartUploadPart(part_number=part_number, etag=etag)

    async def complete_multipart_upload(
        self,
        handle: MultipartUploadHandle,
        parts: list[MultipartUploadPart],
    ) -> StorageResult:
        if not parts:
            raise ValueError("Multipart upload requires at least one part")
        ordered = sorted(parts, key=lambda part: part.part_number)
        client = await self._s3_client()
        try:
            resp = await self._operate(
                "multipart_complete",
                handle.key,
                lambda: client.complete_multipart_upload(
                    Bucket=self._bucket,
                    Key=handle.key,
                    UploadId=handle.upload_id,
                    MultipartUpload={
                        "Parts": [
                            {"ETag": part.etag, "PartNumber": part.part_number}
                            for part in ordered
                        ],
                    },
                ),
            )
        finally:
            await self._close_client(client)
        return StorageResult(
            key=handle.key,
            etag=resp.get("ETag", ""),
            version_id=resp.get("VersionId"),
            public_url=self.get_public_url(handle.key),
        )

    async def abort_multipart_upload(self, handle: MultipartUploadHandle) -> None:
        client = await self._s3_client()
        try:
            await self._operate(
                "multipart_abort",
                handle.key,
                lambda: client.abort_multipart_upload(
                    Bucket=self._bucket,
                    Key=handle.key,
                    UploadId=handle.upload_id,
                ),
            )
        finally:
            await self._close_client(client)

    async def upload_multipart(
        self,
        key: str,
        stream: AsyncIterator[bytes],
        mimetype: str,
        *,
        part_size_bytes: int | None = None,
    ) -> StorageResult:
        part_size = part_size_bytes or DEFAULT_MULTIPART_PART_SIZE
        if (
            not isinstance(part_size, int)
            or isinstance(part_size, bool)
            or part_size < MIN_MULTIPART_PART_SIZE
        ):
            raise ValueError("Multipart partSizeBytes must be at least 5 MiB")
        handle = await self.create_multipart_upload(key, mimetype)
        parts: list[MultipartUploadPart] = []
        pending = b""
        part_number = 1
        try:
            async for chunk in stream:
                pending += chunk
                while len(pending) >= part_size:
                    body = pending[:part_size]
                    pending = pending[part_size:]
                    parts.append(
                        await self.upload_part(handle, part_number=part_number, body=body),
                    )
                    part_number += 1
            if pending or not parts:
                parts.append(
                    await self.upload_part(handle, part_number=part_number, body=pending),
                )
            return await self.complete_multipart_upload(handle, parts)
        except Exception:
            with suppress(Exception):
                await self.abort_multipart_upload(handle)
            raise

    async def delete(self, key: str) -> None:
        client = await self._s3_client()
        try:
            await self._operate(
                "delete",
                key,
                lambda: client.delete_object(Bucket=self._bucket, Key=key),
            )
        finally:
            await self._close_client(client)

    async def get_stream(self, key: str) -> AsyncIterator[bytes]:
        if self._closed or (self._closing and self._operation_depth == 0):
            raise StorageError(
                "Storage client is not accepting operations",
                code=MEDIA_STORAGE_CLOSED,
                metadata={"operation": "get_stream"},
            )
        client = await self._s3_client()
        self._active_operations += 1
        try:
            resp = await client.get_object(Bucket=self._bucket, Key=key)
            body: Any = resp["Body"]
            while True:
                chunk = await body.read(_STREAM_CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk
        except Exception as exc:
            code = "MEDIA_GET_STREAM_FAILED"
            raise StorageError(
                "Storage operation failed",
                code=code,
                metadata={"operation": "get_stream", "key": key},
            ) from exc
        finally:
            self._active_operations -= 1
            if self._active_operations == 0:
                self._notify_drain_waiters()
            await self._close_client(client)

    async def get(self, key: str) -> bytes | None:
        try:
            chunks = [chunk async for chunk in self.get_stream(key)]
        except StorageError as exc:
            if _is_no_such_key(exc.__cause__):
                return None
            raise
        return b"".join(chunks)

    async def get_signed_upload_url(self, key: str, mimetype: str, ttl: int | None = None) -> str:
        client = await self._s3_client()
        try:
            url: str = await self._operate(
                "sign_upload",
                key,
                lambda: self._presigned_put(client, key, mimetype, ttl),
            )
        finally:
            await self._close_client(client)
        return url

    async def get_signed_download_url(self, key: str, ttl: int | None = None) -> str:
        client = await self._s3_client()
        try:
            url: str = await self._operate(
                "sign_download",
                key,
                lambda: self._presigned_get(client, key, ttl),
            )
        finally:
            await self._close_client(client)
        return url

    def get_public_url(self, key: str) -> str:
        if self._public_url:
            base = self._public_url.rstrip("/")
        else:
            base = self._endpoint.rstrip("/")
            base = f"{base}/{_urlencode(self._bucket)}"
        encoded_key = "/".join(_urlencode(segment) for segment in key.split("/"))
        return f"{base}/{encoded_key}"

    async def health(self) -> StorageHealth:
        if self._closed:
            return StorageHealth(healthy=False, status="closed")
        started = monotonic()
        client = await self._s3_client()
        try:
            await self._operate(
                "health",
                self._bucket,
                lambda: client.head_bucket(Bucket=self._bucket),
            )
        except StorageError as exc:
            elapsed = _elapsed_ms(started)
            if exc.code == MEDIA_STORAGE_CLOSED:
                return StorageHealth(healthy=False, status="closed", latency_ms=elapsed)
            return StorageHealth(
                healthy=False,
                status="unavailable",
                latency_ms=elapsed,
                error=_cause_message(exc),
            )
        except Exception as exc:
            return StorageHealth(
                healthy=False,
                status="unavailable",
                latency_ms=_elapsed_ms(started),
                error=str(exc),
            )
        else:
            return StorageHealth(
                healthy=True,
                status="ready",
                latency_ms=_elapsed_ms(started),
            )
        finally:
            await self._close_client(client)

    def status(self) -> StorageStatus:
        if self._closed:
            return "closed"
        return "closing" if self._closing else "ready"

    def diagnostics(self) -> dict[str, object]:
        return {
            "status": self.status(),
            "active_operations": self._active_operations,
            "bucket": self._bucket,
            "endpoint": self._endpoint,
            "region": self._region,
        }

    async def drain(self, timeout_ms: int = 10_000) -> None:
        if self._active_operations == 0:
            return
        waiter: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._drain_waiters.add(waiter)
        try:
            await asyncio.wait_for(waiter, timeout_ms / 1000)
        except TimeoutError as exc:
            raise StorageError(
                f"Storage drain timed out after {timeout_ms}ms",
                code=MEDIA_DRAIN_TIMEOUT,
                metadata={
                    "timeout_ms": timeout_ms,
                    "active_operations": self._active_operations,
                },
            ) from exc
        finally:
            self._drain_waiters.discard(waiter)

    async def close(self) -> None:
        if self._closed or self._closing:
            return
        self._closing = True
        try:
            await self.drain()
        finally:
            self._closed = True
            self._closing = False

    async def shutdown(self) -> None:
        await self.close()


def _validate_options(*, endpoint: str, region: str, bucket: str, link_ttl: int) -> None:
    if not endpoint or not region or not bucket:
        raise ValueError("Storage region, endpoint, and bucket are required")
    if not isinstance(link_ttl, int) or isinstance(link_ttl, bool) or link_ttl <= 0:
        raise ValueError("Storage linkTTL must be a positive integer")


def _urlencode(segment: str) -> str:
    return quote(segment, safe="")


def _elapsed_ms(started: float) -> int:
    return int((monotonic() - started) * 1000)


def _cause_message(exc: BaseException) -> str:
    cause = exc.__cause__
    if cause is not None:
        return str(cause)
    return str(exc)


def _is_no_such_key(exc: BaseException | None) -> bool:
    if exc is None:
        return False
    code: str | None = None
    if hasattr(exc, "response") and isinstance(exc.response, dict):
        err = exc.response.get("Error", {})
        if isinstance(err, dict):
            code = err.get("Code")
    return code in ("NoSuchKey", "NotFound")
