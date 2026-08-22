"""Behaviour tests for the storage data models and the FileStorage contract."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from media import S3StorageService
from media.model import (
    FileStorage,
    MultipartUploadHandle,
    MultipartUploadPart,
    StorageHealth,
    StorageResult,
)


def test_storage_result_defaults() -> None:
    result = StorageResult(key="a", etag="etag")
    assert result.key == "a"
    assert result.etag == "etag"
    assert result.version_id is None
    assert result.public_url == ""


def test_storage_result_full() -> None:
    result = StorageResult(key="a", etag="etag", version_id="v1", public_url="https://cdn/x")
    assert result.version_id == "v1"
    assert result.public_url == "https://cdn/x"


def test_multipart_models_are_frozen() -> None:
    handle = MultipartUploadHandle(key="a", upload_id="u1")
    part = MultipartUploadPart(part_number=1, etag="e1")
    assert (handle.key, handle.upload_id) == ("a", "u1")
    assert (part.part_number, part.etag) == (1, "e1")
    with pytest.raises(FrozenInstanceError):
        handle.upload_id = "u2"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        part.etag = "e2"  # type: ignore[misc]


def test_storage_health_ready() -> None:
    health = StorageHealth(healthy=True, status="ready", latency_ms=12)
    assert health.healthy is True
    assert health.status == "ready"
    assert health.latency_ms == 12
    assert health.error is None


def test_storage_health_closed() -> None:
    health = StorageHealth(healthy=False, status="closed")
    assert health.healthy is False
    assert health.status == "closed"


def test_s3_service_implements_file_storage_protocol() -> None:
    service = S3StorageService()
    assert isinstance(service, FileStorage)
