"""Smoke test - verifies omnixys-media can be imported."""

from __future__ import annotations

import importlib



def test_package_importable() -> None:
    mod = importlib.import_module("omnixys_media")
    assert hasattr(mod, "__version__")
    assert mod.__version__ == "1.0.0"


def test_public_api() -> None:
    from omnixys_media import model, s3

    assert model is not None
    assert s3 is not None
