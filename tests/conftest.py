# @license GPL-3.0-or-later
# Copyright (C) 2025 Caleb Gyamfi - Omnixys Technologies
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# For more information, visit <https://www.gnu.org/licenses/>.

"""Shared fakes and fixtures for behaviour tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from media import S3StorageService


class FakeBody:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self, amt: int | None = None) -> bytes:
        if amt is None:
            chunk, self._data = self._data, b""
            return chunk
        chunk, self._data = self._data[:amt], self._data[amt:]
        return chunk


class NoSuchKeyError(Exception):
    def __init__(self) -> None:
        super().__init__("The specified key does not exist.")
        self.response = {"Error": {"Code": "NoSuchKey"}}


class FakeClient:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.aborted: list[str] = []
        self.upload_id_counter = 0
        self.part_counter = 0
        self.fail_put = False
        self.head_fails = False
        self.missing_upload_id = False
        self.missing_etag = False
        self.block_event: asyncio.Event | None = None

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False

    def _record(self, operation: str, **kwargs: Any) -> None:
        self.calls.append((operation, kwargs))

    async def put_object(self, **kwargs: Any) -> dict[str, str]:
        self._record("put_object", **kwargs)
        if self.fail_put:
            raise OSError("boom")
        self.objects[kwargs["Key"]] = kwargs["Body"]
        return {"ETag": f"etag-{len(self.objects)}", "VersionId": "v1"}

    async def get_object(self, **kwargs: Any) -> dict[str, FakeBody]:
        self._record("get_object", **kwargs)
        if self.block_event is not None:
            await self.block_event.wait()
        key = kwargs["Key"]
        if key not in self.objects:
            raise NoSuchKeyError()
        return {"Body": FakeBody(self.objects[key])}

    async def delete_object(self, **kwargs: Any) -> dict[str, Any]:
        self._record("delete_object", **kwargs)
        self.objects.pop(kwargs["Key"], None)
        return {}

    async def head_bucket(self, **kwargs: Any) -> dict[str, Any]:
        self._record("head_bucket", **kwargs)
        if self.head_fails:
            raise OSError("bucket unavailable")
        return {}

    async def create_multipart_upload(self, **kwargs: Any) -> dict[str, Any]:
        self._record("create_multipart_upload", **kwargs)
        if self.missing_upload_id:
            return {}
        self.upload_id_counter += 1
        return {"UploadId": f"upload-{self.upload_id_counter}"}

    async def upload_part(self, **kwargs: Any) -> dict[str, Any]:
        self._record("upload_part", **kwargs)
        if self.missing_etag:
            return {}
        self.part_counter += 1
        return {"ETag": f"part-etag-{self.part_counter}"}

    async def complete_multipart_upload(self, **kwargs: Any) -> dict[str, str]:
        self._record("complete_multipart_upload", **kwargs)
        self.part_counter += 1
        return {"ETag": f"final-etag-{self.part_counter}", "VersionId": "v2"}

    async def abort_multipart_upload(self, **kwargs: Any) -> dict[str, Any]:
        self._record("abort_multipart_upload", **kwargs)
        self.aborted.append(kwargs["UploadId"])
        return {}

    def generate_presigned_url(self, method: str, Params: dict[str, Any], ExpiresIn: int) -> str:
        self._record("presign", method=method, params=Params, expires_in=ExpiresIn)
        return f"https://signed.example/{method}?ttl={ExpiresIn}"


class FakeSession:
    def __init__(self, client: FakeClient) -> None:
        self._client = client

    async def create_client(self, *_: Any, **__: Any) -> FakeClient:
        return self._client


@pytest.fixture
def make_service() -> Any:
    def _make(**overrides: Any) -> tuple[S3StorageService, FakeClient]:
        client = FakeClient()
        service = S3StorageService(**overrides)
        service._session = FakeSession(client)
        return service, client

    return _make


async def async_chunks(items: list[bytes]) -> AsyncIterator[bytes]:
    for item in items:
        yield item
