from __future__ import annotations

from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from media.s3 import S3StorageService


class MediaProvider(Provider):
    def __init__(  # noqa: PLR0913
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
    ) -> None:
        super().__init__()
        self._endpoint = endpoint
        self._region = region
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._bucket = bucket
        self._force_path_style = force_path_style
        self._link_ttl = link_ttl
        self._public_url = public_url

    @provide(scope=Scope.APP)
    async def storage(self) -> AsyncIterator[S3StorageService]:
        service = S3StorageService(
            endpoint=self._endpoint,
            region=self._region,
            access_key_id=self._access_key_id,
            secret_access_key=self._secret_access_key,
            bucket=self._bucket,
            force_path_style=self._force_path_style,
            link_ttl=self._link_ttl,
            public_url=self._public_url,
        )
        try:
            yield service
        finally:
            await service.close()
