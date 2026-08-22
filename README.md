# omnixys-media

Async S3/MinIO storage toolkit for Omnixys services, built on `aiobotocore`.
It mirrors the behaviour of the TypeScript `@omnixys/media` package
(`MinioStorageService` / `FileStorage`): the same operation set, the same
`MEDIA_*` error codes, and the same graceful-shutdown lifecycle.

## Installation

```bash
pip install omnixys-media
```

## Features

- **S3StorageService** — `FileStorage` implementation backed by aiobotocore (path or virtual addressing, TLS, presigned URLs).
- **Upload** — `upload` (bytes), `upload_stream` (async iterable), and a full **multipart** flow (`upload_multipart`, `create_multipart_upload`, `upload_part`, `complete_multipart_upload`, `abort_multipart_upload`).
- **Download** — `get` (buffered bytes, `None` for missing keys) and `get_stream` (chunked async iterator).
- **Signed links** — `get_signed_upload_url` / `get_signed_download_url` with a configurable `link_ttl`.
- **Public URLs** — `get_public_url` with percent-encoded bucket/key segments and an optional CDN base.
- **Health & lifecycle** — `health()`, `status()`, `diagnostics()`, `drain()`, `close()`, `shutdown()`; in-flight operations are drained before shutdown and new operations are rejected afterwards.
- **Stable error codes** — every failure is raised as `StorageError` with a TS-compatible `code` and structured `metadata`.
- **Dishka wiring** — `MediaProvider` provides an app-scoped service and closes it when the container closes.

## Quick start

```python
import asyncio

from media import S3StorageService

async def main() -> None:
    storage = S3StorageService(
        endpoint="http://localhost:9000",
        region="us-east-1",
        access_key_id="minioadmin",
        secret_access_key="minioadmin",
        bucket="omnixys",
        link_ttl=3600,                 # TTL for signed URLs
        public_url="https://cdn.example.com",  # optional CDN base
    )

    result = await storage.upload("avatars/42.png", image_bytes, "image/png")
    print(result.key, result.etag, result.public_url)

    data = await storage.get("avatars/42.png")   # None when the key is missing
    await storage.delete("avatars/42.png")
    await storage.shutdown()

asyncio.run(main())
```

Constructor options are validated up front: `endpoint`, `region`, and `bucket`
are required (non-empty) and `link_ttl` must be a positive integer.

## Uploads

```python
# bytes
result = await storage.upload("a/b.txt", b"hello", "text/plain")

# async stream (buffered)
async def chunks():
    yield b"one-"
    yield b"two-"
    yield b"three"

result = await storage.upload_stream("a/b.txt", chunks(), "text/plain")

# multipart for large files (parts are flushed as the stream yields)
result = await storage.upload_multipart("big.bin", chunks(), "application/octet-stream")
```

`upload` sets `CacheControl: public, max-age=31536000, immutable` and returns a
`StorageResult` (`key`, `etag`, `version_id`, `public_url`). Multipart parts
default to 8 MiB and must be at least 5 MiB; `upload_multipart` aborts the
upload automatically if streaming or completion fails.

For manual control the low-level steps are exposed:

```python
handle = await storage.create_multipart_upload("big.bin", "application/octet-stream")
part = await storage.upload_part(handle, part_number=1, body=chunk)   # ValueError for part_number < 1
result = await storage.complete_multipart_upload(handle, [part])      # parts are sorted internally
# or
await storage.abort_multipart_upload(handle)
```

## Downloads

```python
data = await storage.get("a/b.txt")          # bytes | None (None for missing keys)
async for chunk in storage.get_stream("a/b.txt"):
    ...
```

`get_stream` yields 1 MiB chunks and tracks the open stream as an active
operation, so `drain()` will not finish while a stream is being read. Missing
keys yield `None` from `get`, but raise `StorageError` (`MEDIA_GET_STREAM_FAILED`)
from `get_stream`.

## Signed links and public URLs

```python
upload_url = await storage.get_signed_upload_url("a/b.txt", "text/plain")  # ttl default: link_ttl
download_url = await storage.get_signed_download_url("a/b.txt", ttl=60)
public_url = storage.get_public_url("a/b.txt")
```

`signed upload` URLs are intended to be combined with `get_public_url(key)` as
the resulting file URL. `get_public_url` percent-encodes each key segment and
the bucket name; when `public_url` is configured it is used as the base.

## Health and lifecycle

```python
health = await storage.health()
# StorageHealth(healthy=True, status='ready', latency_ms=12)
# StorageHealth(healthy=False, status='unavailable', error='...')

assert storage.status() == "ready"     # 'ready' | 'closing' | 'closed'
storage.diagnostics()                  # status, active_operations, bucket, endpoint, region

await storage.drain(timeout_ms=10_000) # waits for in-flight operations (MEDIA_DRAIN_TIMEOUT)
await storage.close()                  # drain + reject new operations
await storage.shutdown()               # alias of close
```

After `close()`, every operation raises `StorageError` with
`MEDIA_STORAGE_CLOSED`. `health()` instead reports `status='closed'`.

## Dependency injection

```python
from dishka import make_async_container
from media import MediaProvider, S3StorageService

container = make_async_container(
    MediaProvider(
        endpoint="http://localhost:9000",
        bucket="omnixys",
        public_url="https://cdn.example.com",
    )
)

storage = await container.get(S3StorageService)
await storage.upload("a/b.txt", b"x", "text/plain")

# storage is closed automatically when the container closes
await container.close()
```

## Errors

All failures are raised as `StorageError` and carry a TS-compatible `code`
plus structured `metadata`:

```python
from media import StorageError

try:
    await storage.upload("f", b"x", "text/plain")
except StorageError as exc:
    print(exc.code)      # e.g. "MEDIA_UPLOAD_FAILED"
    print(exc.metadata)  # e.g. {"operation": "upload", "key": "f"}
    print(exc.__cause__) # original provider error
```

Per-operation codes: `MEDIA_UPLOAD_FAILED`, `MEDIA_UPLOAD_STREAM_FAILED`,
`MEDIA_UPLOAD_MULTIPART_FAILED`, `MEDIA_MULTIPART_CREATE_FAILED`,
`MEDIA_MULTIPART_PART_FAILED`, `MEDIA_MULTIPART_COMPLETE_FAILED`,
`MEDIA_MULTIPART_ABORT_FAILED`, `MEDIA_DELETE_FAILED`, `MEDIA_GET_FAILED`,
`MEDIA_GET_STREAM_FAILED`, `MEDIA_SIGN_UPLOAD_FAILED`,
`MEDIA_SIGN_DOWNLOAD_FAILED`, `MEDIA_HEALTH_FAILED`.

Special codes: `MEDIA_STORAGE_CLOSED`, `MEDIA_DRAIN_TIMEOUT`,
`MEDIA_MULTIPART_ID_MISSING`, `MEDIA_MULTIPART_ETAG_MISSING`,
`MEDIA_BODY_UNSUPPORTED`.

Input-validation failures (`partSizeBytes`, `partNumber`, empty options)
raise `ValueError`, mirroring the TS `RangeError`/`TypeError` contract.

## Development

```bash
uv sync
uv run pytest -q
uv run ruff check .
uv run mypy src/
```

## License

GPL-3.0-or-later
