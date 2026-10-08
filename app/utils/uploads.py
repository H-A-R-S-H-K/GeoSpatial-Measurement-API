"""Read an upload without buffering more than the configured limit."""

from starlette.datastructures import UploadFile

from app.core.exceptions import UploadTooLargeError

_READ_CHUNK_BYTES = 1024 * 1024


async def read_limited_upload(upload: UploadFile, max_bytes: int) -> bytes:
    """Read the upload in chunks and stop once it exceeds ``max_bytes``."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise UploadTooLargeError(f"Upload exceeds the maximum size of {max_bytes} bytes.")
        chunks.append(chunk)
    return b"".join(chunks)
