from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiobotocore.session import get_session

from media.errors import StorageError
from media.model import StorageResult

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from botocore.config import Config


class S3StorageService:
    def __init__(  # noqa: PLR0913
        self,
        endpoint: str = "http://localhost:9000",
        region: str = "us-east-1",
        access_key_id: str = "minioadmin",
        secret_access_key: str = "minioadmin",
        bucket: str = "omnixys",
        *,
        force_path_style: bool = True,
        link_ttl: int = 3600,
        public_url: str = "",
    ) -> None:
        self._endpoint = endpoint
        self._region = region
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._bucket = bucket
        self._force_path_style = force_path_style
        self._link_ttl = link_ttl
        self._public_url = public_url
        self._session = get_session()

    async def _s3_client(self) -> Any:
        s3_config = Config(
            s3={"addressing_style": "path" if self._force_path_style else "virtual"},
        )
        return await self._session.create_client(
            "s3",
            region_name=self._region,
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key_id,
            aws_secret_access_key=self._secret_access_key,
            use_ssl=self._endpoint.startswith("https"),
            config=s3_config,
        ).__aenter__()

    async def _close_client(self, client: Any) -> None:
        await client.__aexit__(None, None, None)

    async def upload(self, key: str, data: bytes, mimetype: str) -> StorageResult:
        client = await self._s3_client()
        try:
            resp = await client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=mimetype,
            )
            return StorageResult(
                key=key,
                etag=resp.get("ETag", ""),
                version_id=resp.get("VersionId"),
            )
        finally:
            await self._close_client(client)

    async def upload_stream(self, key: str, stream: AsyncIterator[bytes], mimetype: str) -> StorageResult:
        chunks = [chunk async for chunk in stream]
        data = b"".join(chunks)
        return await self.upload(key=key, data=data, mimetype=mimetype)

    async def delete(self, key: str) -> None:
        client = await self._s3_client()
        try:
            await client.delete_object(Bucket=self._bucket, Key=key)
        finally:
            await self._close_client(client)

    async def get(self, key: str) -> bytes | None:
        client = await self._s3_client()
        try:
            resp = await client.get_object(Bucket=self._bucket, Key=key)
            body = await resp["Body"].read()
        except Exception as exc:
            if _is_no_such_key(exc):
                return None
            raise StorageError(str(exc), code="STORAGE_ERROR") from exc
        else:
            return body  # type: ignore[no-any-return]
        finally:
            await self._close_client(client)

    async def get_signed_upload_url(self, key: str, mimetype: str, ttl: int | None = None) -> str:
        client = await self._s3_client()
        try:
            url = await client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": key,
                    "ContentType": mimetype,
                },
                ExpiresIn=ttl or self._link_ttl,
            )
            return str(url)
        finally:
            await self._close_client(client)

    async def get_signed_download_url(self, key: str, ttl: int | None = None) -> str:
        client = await self._s3_client()
        try:
            url = await client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": key,
                },
                ExpiresIn=ttl or self._link_ttl,
            )
            return str(url)
        finally:
            await self._close_client(client)

    def get_public_url(self, key: str) -> str:
        if self._public_url:
            base = self._public_url.rstrip("/")
            return f"{base}/{key}"
        endpoint = self._endpoint.rstrip("/")
        return f"{endpoint}/{self._bucket}/{key}"

    async def health(self) -> bool:
        client = await self._s3_client()
        try:
            await client.head_bucket(Bucket=self._bucket)
        except Exception:  # noqa: BLE001
            return False
        else:
            return True
        finally:
            await self._close_client(client)


def _is_no_such_key(exc: Exception) -> bool:
    code: str | None = None
    if hasattr(exc, "response") and isinstance(exc.response, dict):
        err = exc.response.get("Error", {})
        if isinstance(err, dict):
            code = err.get("Code")
    return code in ("NoSuchKey", "NotFound")
