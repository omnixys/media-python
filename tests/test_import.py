"""Smoke test - verifies omnixys-media can be imported."""

from __future__ import annotations

import importlib
from importlib.metadata import version as pkg_version


def test_package_importable() -> None:
    mod = importlib.import_module("media")
    assert mod is not None


def test_package_version() -> None:
    assert pkg_version("omnixys-media")


def test_public_api() -> None:
    from media import model, s3

    assert model is not None
    assert s3 is not None
