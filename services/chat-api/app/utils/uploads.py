from __future__ import annotations

from fastapi import HTTPException, UploadFile


async def read_upload_with_limit(
    file: UploadFile,
    *,
    max_bytes: int,
    label: str,
    chunk_size: int = 1024 * 1024,
) -> bytes:
    """Read an UploadFile with a configurable hard size limit."""
    limit = int(max_bytes or 0)
    if limit <= 0:
        return await file.read()

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail=f"{label} is too large. Maximum allowed size is {limit} bytes.",
            )
        chunks.append(chunk)
    return b"".join(chunks)
