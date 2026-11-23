"""UNA Watch file mirror (plan 0023).

Two routes, shaped like the scale drain's (plan 0015 §4): the phone reads
the manifest, fetches over BLE only what differs, and hands each verified file
back. The server decides what is new; the phone remembers nothing.
"""

import logging

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel

from app.services import watch_store

logger = logging.getLogger(__name__)

router = APIRouter()


class WatchFileOut(BaseModel):
    path: str
    size: int
    # A decimal string: the watch's raw uint64 timestamp, compared verbatim
    # and never interpreted (its unit differs between the doc and firmware).
    mtime: str
    crc32: int
    received_at: str


class WatchManifest(BaseModel):
    files: list[WatchFileOut]


class WatchUploadResult(BaseModel):
    path: str
    status: str  # stored | touched | unchanged
    stored_as: str


@router.get("/files", response_model=WatchManifest)
def list_files():
    """Everything already held, by watch path: the phone's diff baseline."""
    entries = sorted(watch_store.current().values(), key=lambda e: e.path)
    return WatchManifest(
        files=[
            WatchFileOut(
                path=e.path, size=e.size, mtime=e.mtime, crc32=e.crc32, received_at=e.received_at
            )
            for e in entries
        ]
    )


@router.put("/files", response_model=WatchUploadResult)
async def upload_file(
    request: Request,
    path: str = Query(..., description="Absolute path on the watch"),
    x_watch_size: int = Header(...),
    x_watch_mtime: str = Header(...),
    x_watch_crc32: str = Header(..., description="CRC-32 as 8 hex digits"),
):
    """Keep one file read off the watch, after checking it is what it claims.

    The body is the raw bytes. PUT, because uploading the same file twice is
    the same as uploading it once.
    """
    if x_watch_size > watch_store.MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File too large")
    try:
        crc = int(x_watch_crc32, 16)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="X-Watch-Crc32 must be hex") from exc

    body = await request.body()
    try:
        outcome, entry = watch_store.store(
            path, body, size=x_watch_size, mtime=x_watch_mtime, crc32=crc
        )
    except watch_store.WatchFileRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    logger.info("Watch file %s: %s (%d bytes)", entry.path, outcome, entry.size)
    return WatchUploadResult(path=entry.path, status=outcome, stored_as=entry.stored_as)
