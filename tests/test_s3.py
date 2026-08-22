"""Behaviour tests for S3StorageService (mirroring the TS MinioStorageService)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

import media.s3 as media_s3
from media import S3StorageService
from media.errors import StorageError
from media.model import MultipartUploadHandle, MultipartUploadPart
from tests.conftest import async_chunks

CACHE_CONTROL_IMMUTABLE = "public, max-age=31536000, immutable"


async def test_upload_returns_result_and_sets_cache_control(make_service) -> None:
    service, client = make_service(public_url="https://cdn.example.com/media")
    result = await service.upload("a/b.txt", b"hello", "text/plain")

    assert result.key == "a/b.txt"
    assert result.etag == "etag-1"
    assert result.version_id == "v1"
    assert result.public_url == "https://cdn.example.com/media/a/b.txt"

    operation, kwargs = client.calls[0]
    assert operation == "put_object"
    assert kwargs["Bucket"] == "omnixys"
    assert kwargs["Key"] == "a/b.txt"
    assert kwargs["ContentType"] == "text/plain"
    assert kwargs["Body"] == b"hello"
    assert kwargs["CacheControl"] == CACHE_CONTROL_IMMUTABLE


async def test_upload_stream_buffers_chunks(make_service) -> None:
    service, client = make_service()
    result = await service.upload_stream(
        "f", async_chunks([b"one-", b"two-", b"three"]), "text/plain",
    )

    assert client.objects["f"] == b"one-two-three"
    assert result.key == "f"
    assert result.public_url.startswith("http://localhost:9000/")


async def test_upload_wraps_underlying_error(make_service) -> None:
    service, client = make_service()
    client.fail_put = True

    with pytest.raises(StorageError) as exc_info:
        await service.upload("f", b"x", "text/plain")

    assert exc_info.value.code == "MEDIA_UPLOAD_FAILED"
    assert exc_info.value.metadata == {"operation": "upload", "key": "f"}
    assert isinstance(exc_info.value.__cause__, OSError)


async def test_upload_stream_wraps_stream_error(make_service) -> None:
    service, _ = make_service()

    async def broken() -> AsyncIterator[bytes]:
        yield b"x"
        raise OSError("stream broke")

    with pytest.raises(StorageError) as exc_info:
        await service.upload_stream("f", broken(), "text/plain")

    assert exc_info.value.code == "MEDIA_UPLOAD_STREAM_FAILED"


async def test_get_returns_bytes(make_service) -> None:
    service, client = make_service()
    client.objects["f"] = b"payload"

    assert await service.get("f") == b"payload"


async def test_get_returns_none_for_missing_key(make_service) -> None:
    service, _ = make_service()

    assert await service.get("missing") is None


async def test_get_stream_yields_chunks(make_service) -> None:
    service, client = make_service()
    payload = b"x" * (3 * 1024 * 1024)
    client.objects["f"] = payload

    chunks = [chunk async for chunk in service.get_stream("f")]

    assert b"".join(chunks) == payload
    assert len(chunks) == 3


async def test_get_stream_missing_key_raises(make_service) -> None:
    service, _ = make_service()

    with pytest.raises(StorageError) as exc_info:
        async for _ in service.get_stream("missing"):
            pass

    assert exc_info.value.code == "MEDIA_GET_STREAM_FAILED"


async def test_delete_removes_object(make_service) -> None:
    service, client = make_service()
    client.objects["f"] = b"data"

    await service.delete("f")

    assert "f" not in client.objects


async def test_get_signed_upload_url_uses_link_ttl(make_service) -> None:
    service, client = make_service(link_ttl=600)

    url = await service.get_signed_upload_url("f", "image/png")

    assert url == "https://signed.example/put_object?ttl=600"
    operation, kwargs = client.calls[0]
    assert operation == "presign"
    assert kwargs["expires_in"] == 600
    assert kwargs["params"] == {
        "Bucket": "omnixys",
        "Key": "f",
        "ContentType": "image/png",
    }


async def test_get_signed_download_url_overrides_ttl(make_service) -> None:
    service, client = make_service(link_ttl=3600)

    url = await service.get_signed_download_url("f", ttl=60)

    assert url == "https://signed.example/get_object?ttl=60"
    operation, kwargs = client.calls[0]
    assert operation == "presign"
    assert kwargs["expires_in"] == 60


def test_get_public_url_uses_custom_base(make_service) -> None:
    service, _ = make_service(public_url="https://cdn.example.com/media/")

    assert service.get_public_url("a/b.txt") == "https://cdn.example.com/media/a/b.txt"


def test_get_public_url_default_endpoint_encodes_bucket_and_key(make_service) -> None:
    service, _ = make_service(endpoint="http://localhost:9000", bucket="my bucket")

    url = service.get_public_url("dir/my file.txt")

    assert url == "http://localhost:9000/my%20bucket/dir/my%20file.txt"


async def test_health_ready(make_service) -> None:
    service, _ = make_service()

    health = await service.health()

    assert health.healthy is True
    assert health.status == "ready"
    assert health.latency_ms is not None
    assert health.error is None


async def test_health_unavailable(make_service) -> None:
    service, client = make_service()
    client.head_fails = True

    health = await service.health()

    assert health.healthy is False
    assert health.status == "unavailable"
    assert health.error == "bucket unavailable"


async def test_health_closed(make_service) -> None:
    service, _ = make_service()
    await service.close()

    health = await service.health()

    assert health.healthy is False
    assert health.status == "closed"


async def test_status_lifecycle_and_idempotent_close(make_service) -> None:
    service, _ = make_service()

    assert service.status() == "ready"
    await service.close()
    assert service.status() == "closed"
    await service.close()
    await service.shutdown()


async def test_operations_rejected_after_close(make_service) -> None:
    service, _ = make_service()
    await service.close()

    with pytest.raises(StorageError) as exc_info:
        await service.upload("f", b"x", "text/plain")
    assert exc_info.value.code == "MEDIA_STORAGE_CLOSED"

    with pytest.raises(StorageError) as exc_info:
        await service.delete("f")
    assert exc_info.value.code == "MEDIA_STORAGE_CLOSED"


async def test_diagnostics(make_service) -> None:
    service, _ = make_service()

    diag = service.diagnostics()

    assert diag["status"] == "ready"
    assert diag["bucket"] == "omnixys"
    assert diag["endpoint"] == "http://localhost:9000"
    assert diag["active_operations"] == 0


async def test_drain_waits_for_active_operations(make_service) -> None:
    service, client = make_service()
    client.objects["f"] = b"data"
    release = asyncio.Event()
    client.block_event = release

    read_task = asyncio.create_task(service.get("f"))
    await asyncio.sleep(0.01)

    drain_task = asyncio.create_task(service.drain())
    await asyncio.sleep(0.01)
    assert not drain_task.done()

    release.set()
    assert await read_task == b"data"
    await drain_task
    assert service.diagnostics()["active_operations"] == 0


async def test_drain_times_out(make_service) -> None:
    service, client = make_service()
    client.objects["f"] = b"data"
    release = asyncio.Event()
    client.block_event = release

    read_task = asyncio.create_task(service.get("f"))
    await asyncio.sleep(0.01)

    with pytest.raises(StorageError) as exc_info:
        await service.drain(timeout_ms=50)

    assert exc_info.value.code == "MEDIA_DRAIN_TIMEOUT"
    assert exc_info.value.metadata["active_operations"] >= 1

    release.set()
    await read_task


async def test_multipart_lifecycle(make_service) -> None:
    service, client = make_service()

    handle = await service.create_multipart_upload("big.bin", "application/octet-stream")
    assert handle == MultipartUploadHandle(key="big.bin", upload_id="upload-1")

    part_one = await service.upload_part(handle, part_number=1, body=b"aaa")
    part_two = await service.upload_part(handle, part_number=2, body=b"bbb")
    assert part_one == MultipartUploadPart(part_number=1, etag="part-etag-1")
    assert part_two == MultipartUploadPart(part_number=2, etag="part-etag-2")

    result = await service.complete_multipart_upload(handle, [part_one, part_two])
    assert result.key == "big.bin"
    assert result.etag == "final-etag-3"
    assert result.version_id == "v2"

    complete_call = next(call for call in client.calls if call[0] == "complete_multipart_upload")
    parts = complete_call[1]["MultipartUpload"]["Parts"]
    assert parts == [
        {"ETag": "part-etag-1", "PartNumber": 1},
        {"ETag": "part-etag-2", "PartNumber": 2},
    ]


async def test_multipart_complete_sorts_parts(make_service) -> None:
    service, client = make_service()
    handle = await service.create_multipart_upload("f", "text/plain")

    part_two = await service.upload_part(handle, part_number=2, body=b"b")
    part_one = await service.upload_part(handle, part_number=1, body=b"a")

    await service.complete_multipart_upload(handle, [part_two, part_one])

    complete_call = next(call for call in client.calls if call[0] == "complete_multipart_upload")
    parts = complete_call[1]["MultipartUpload"]["Parts"]
    assert [part["PartNumber"] for part in parts] == [1, 2]
    assert [part["ETag"] for part in parts] == ["part-etag-2", "part-etag-1"]


async def test_create_multipart_missing_upload_id(make_service) -> None:
    service, client = make_service()
    client.missing_upload_id = True

    with pytest.raises(StorageError) as exc_info:
        await service.create_multipart_upload("f", "text/plain")

    assert exc_info.value.code == "MEDIA_MULTIPART_ID_MISSING"


async def test_upload_part_missing_etag(make_service) -> None:
    service, client = make_service()
    client.missing_etag = True
    handle = await service.create_multipart_upload("f", "text/plain")

    with pytest.raises(StorageError) as exc_info:
        await service.upload_part(handle, part_number=1, body=b"x")

    assert exc_info.value.code == "MEDIA_MULTIPART_ETAG_MISSING"
    assert exc_info.value.metadata == {"key": "f", "part_number": 1}


async def test_upload_part_rejects_invalid_part_number(make_service) -> None:
    service, _ = make_service()
    handle = MultipartUploadHandle(key="f", upload_id="u1")

    with pytest.raises(ValueError):
        await service.upload_part(handle, part_number=0, body=b"x")


async def test_complete_multipart_requires_at_least_one_part(make_service) -> None:
    service, _ = make_service()
    handle = MultipartUploadHandle(key="f", upload_id="u1")

    with pytest.raises(ValueError):
        await service.complete_multipart_upload(handle, [])


async def test_upload_multipart_splits_into_parts(make_service, monkeypatch) -> None:
    service, client = make_service()
    monkeypatch.setattr(media_s3, "MIN_MULTIPART_PART_SIZE", 2)

    result = await service.upload_multipart(
        "big", async_chunks([b"aaabbbcccdd"]), "text/plain", part_size_bytes=3,
    )

    part_bodies = [call[1]["Body"] for call in client.calls if call[0] == "upload_part"]
    assert part_bodies == [b"aaa", b"bbb", b"ccc", b"dd"]
    assert len([call for call in client.calls if call[0] == "complete_multipart_upload"]) == 1
    assert result.key == "big"
    assert result.etag == "final-etag-5"


async def test_upload_multipart_aborts_on_failure(make_service, monkeypatch) -> None:
    service, client = make_service()
    monkeypatch.setattr(media_s3, "MIN_MULTIPART_PART_SIZE", 2)

    async def broken() -> AsyncIterator[bytes]:
        yield b"aaa"
        raise OSError("network down")

    with pytest.raises(OSError):
        await service.upload_multipart(
            "f", broken(), "text/plain", part_size_bytes=3,
        )

    assert client.aborted == ["upload-1"]


async def test_upload_multipart_rejects_small_part_size(make_service) -> None:
    service, _ = make_service()

    with pytest.raises(ValueError):
        await service.upload_multipart(
            "f", async_chunks([b"x"]), "text/plain", part_size_bytes=1024,
        )


def test_validate_options_rejects_missing_values() -> None:
    with pytest.raises(ValueError):
        S3StorageService(endpoint="", region="us-east-1", bucket="b")
    with pytest.raises(ValueError):
        S3StorageService(endpoint="http://localhost:9000", region="", bucket="b")
    with pytest.raises(ValueError):
        S3StorageService(endpoint="http://localhost:9000", region="us-east-1", bucket="")


def test_validate_options_rejects_non_positive_ttl() -> None:
    with pytest.raises(ValueError):
        S3StorageService(link_ttl=0)
    with pytest.raises(ValueError):
        S3StorageService(link_ttl=-10)
