"""Behaviour tests for StorageError and the MEDIA_* error-code catalogue."""

from __future__ import annotations

from media import errors
from media.errors import StorageError


def test_default_code_is_storage_error() -> None:
    err = StorageError("boom")
    assert err.code == "STORAGE_ERROR"
    assert err.code == errors.STORAGE_ERROR
    assert err.metadata == {}
    assert str(err) == "boom"


def test_code_and_metadata_are_stored() -> None:
    err = StorageError("failed", code="MEDIA_UPLOAD_FAILED", metadata={"key": "a"})
    assert err.code == "MEDIA_UPLOAD_FAILED"
    assert err.metadata == {"key": "a"}
    assert err.metadata is not None


def test_metadata_defaults_to_empty_dict() -> None:
    err = StorageError("failed", code="MEDIA_GET_FAILED")
    assert err.metadata == {}


def test_operation_error_codes_match_ts_contract() -> None:
    expected = {
        errors.MEDIA_UPLOAD_FAILED: "MEDIA_UPLOAD_FAILED",
        errors.MEDIA_UPLOAD_STREAM_FAILED: "MEDIA_UPLOAD_STREAM_FAILED",
        errors.MEDIA_UPLOAD_MULTIPART_FAILED: "MEDIA_UPLOAD_MULTIPART_FAILED",
        errors.MEDIA_MULTIPART_CREATE_FAILED: "MEDIA_MULTIPART_CREATE_FAILED",
        errors.MEDIA_MULTIPART_PART_FAILED: "MEDIA_MULTIPART_PART_FAILED",
        errors.MEDIA_MULTIPART_COMPLETE_FAILED: "MEDIA_MULTIPART_COMPLETE_FAILED",
        errors.MEDIA_MULTIPART_ABORT_FAILED: "MEDIA_MULTIPART_ABORT_FAILED",
        errors.MEDIA_DELETE_FAILED: "MEDIA_DELETE_FAILED",
        errors.MEDIA_GET_FAILED: "MEDIA_GET_FAILED",
        errors.MEDIA_GET_STREAM_FAILED: "MEDIA_GET_STREAM_FAILED",
        errors.MEDIA_SIGN_UPLOAD_FAILED: "MEDIA_SIGN_UPLOAD_FAILED",
        errors.MEDIA_SIGN_DOWNLOAD_FAILED: "MEDIA_SIGN_DOWNLOAD_FAILED",
        errors.MEDIA_HEALTH_FAILED: "MEDIA_HEALTH_FAILED",
    }
    for code, expected_value in expected.items():
        assert code == expected_value


def test_special_error_codes_match_ts_contract() -> None:
    assert errors.MEDIA_STORAGE_CLOSED == "MEDIA_STORAGE_CLOSED"
    assert errors.MEDIA_DRAIN_TIMEOUT == "MEDIA_DRAIN_TIMEOUT"
    assert errors.MEDIA_MULTIPART_ID_MISSING == "MEDIA_MULTIPART_ID_MISSING"
    assert errors.MEDIA_MULTIPART_ETAG_MISSING == "MEDIA_MULTIPART_ETAG_MISSING"
    assert errors.MEDIA_BODY_UNSUPPORTED == "MEDIA_BODY_UNSUPPORTED"
