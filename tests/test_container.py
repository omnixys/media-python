"""Behaviour tests for the Dishka MediaProvider wiring."""

from __future__ import annotations

from dishka import make_async_container

from media import MediaProvider, S3StorageService


async def test_provider_exposes_storage_service() -> None:
    container = make_async_container(MediaProvider())
    service = await container.get(S3StorageService)

    assert isinstance(service, S3StorageService)
    assert service.status() == "ready"

    await container.close()


async def test_provider_closes_service_on_container_close() -> None:
    container = make_async_container(MediaProvider())
    service = await container.get(S3StorageService)

    assert service.status() == "ready"
    await container.close()

    assert service.status() == "closed"
