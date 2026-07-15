from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class StorageResult:
    key: str
    etag: str
    version_id: str | None = None


@runtime_checkable
class FileStorage(Protocol):
    async def upload(self, key: str, data: bytes, mimetype: str) -> StorageResult: ...

    async def upload_stream(self, key: str, stream: AsyncIterator[bytes], mimetype: str) -> StorageResult: ...

    async def delete(self, key: str) -> None: ...

    async def get(self, key: str) -> bytes | None: ...

    async def get_signed_upload_url(self, key: str, mimetype: str, ttl: int = 3600) -> str: ...

    async def get_signed_download_url(self, key: str, ttl: int = 3600) -> str: ...

    def get_public_url(self, key: str) -> str: ...

    async def health(self) -> bool: ...
