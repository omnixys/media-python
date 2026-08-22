from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

type StorageBody = AsyncIterator[bytes]
"""Stream of raw bytes accepted by the streaming upload/download APIs."""

StorageStatus = Literal["closed", "closing", "ready"]
StorageHealthStatus = Literal["closed", "ready", "unavailable"]


@dataclass(frozen=True)
class StorageResult:
    key: str
    etag: str
    version_id: str | None = None
    public_url: str = ""


@dataclass(frozen=True)
class MultipartUploadHandle:
    key: str
    upload_id: str


@dataclass(frozen=True)
class MultipartUploadPart:
    part_number: int
    etag: str


@dataclass(frozen=True)
class StorageHealth:
    healthy: bool
    status: StorageHealthStatus
    latency_ms: int | None = None
    error: str | None = None


@runtime_checkable
class FileStorage(Protocol):
    """Async S3/MinIO-compatible storage contract (mirrors TS ``FileStorage``)."""

    async def upload(self, key: str, data: bytes, mimetype: str) -> StorageResult: ...

    async def upload_stream(self, key: str, stream: StorageBody, mimetype: str) -> StorageResult: ...

    async def upload_multipart(
        self,
        key: str,
        stream: StorageBody,
        mimetype: str,
        *,
        part_size_bytes: int | None = None,
    ) -> StorageResult: ...

    async def create_multipart_upload(self, key: str, mimetype: str) -> MultipartUploadHandle: ...

    async def upload_part(
        self,
        handle: MultipartUploadHandle,
        *,
        part_number: int,
        body: bytes,
    ) -> MultipartUploadPart: ...

    async def complete_multipart_upload(
        self,
        handle: MultipartUploadHandle,
        parts: list[MultipartUploadPart],
    ) -> StorageResult: ...

    async def abort_multipart_upload(self, handle: MultipartUploadHandle) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def get(self, key: str) -> bytes | None: ...

    def get_stream(self, key: str) -> AsyncIterator[bytes]: ...

    async def get_signed_upload_url(self, key: str, mimetype: str, ttl: int | None = None) -> str: ...

    async def get_signed_download_url(self, key: str, ttl: int | None = None) -> str: ...

    def get_public_url(self, key: str) -> str: ...

    async def health(self) -> StorageHealth: ...

    def status(self) -> StorageStatus: ...

    def diagnostics(self) -> dict[str, object]: ...

    async def drain(self, timeout_ms: int = 10_000) -> None: ...

    async def close(self) -> None: ...

    async def shutdown(self) -> None: ...
