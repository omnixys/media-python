from __future__ import annotations

from typing import TYPE_CHECKING

from dishka import Provider, Scope, provide

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from omnixys_media.s3 import S3StorageService


class MediaProvider(Provider):  # type: ignore[misc]
    @provide(scope=Scope.APP)  # type: ignore[untyped-decorator]
    async def storage(  # noqa: PLR0913
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
    ) -> AsyncIterator[S3StorageService]:
        service = S3StorageService(
            endpoint=endpoint,
            region=region,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            bucket=bucket,
            force_path_style=force_path_style,
            link_ttl=link_ttl,
            public_url=public_url,
        )
        yield service
