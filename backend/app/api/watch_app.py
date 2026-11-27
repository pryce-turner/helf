"""The watch app (Sleep Log, plan 0024): what is published, and the file itself.

Built by the Dockerfile's `watch-build` stage and copied onto the data volume
by the `helf-watch-app` service (`scripts/publish-watch-app.sh`, plan 0026),
into `settings.watch_apps_dir`. The phone downloads it from here and writes it
to the watch over Bluetooth (`frontend/src/lib/ftsInstall.ts`). Nothing here
builds anything or talks to the watch.
"""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import settings
from app.models.watch_app import WatchAppInfo

# Two routers for the same reason as android_app.py: /download/ is outside
# the service worker's NetworkFirst /api/ route, so the file is never cached.
router = APIRouter()
download_router = APIRouter()

META_FILE = "watch-app.json"


def _meta() -> dict | None:
    try:
        meta = json.loads((settings.watch_apps_dir / META_FILE).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(meta, dict) or not isinstance(meta.get("file_name"), str):
        return None
    # Only a plain file name: it is joined to a directory below.
    name = meta["file_name"]
    if "/" in name or "\\" in name or name.startswith(".") or not name.endswith(".uapp"):
        return None
    if not (settings.watch_apps_dir / name).is_file():
        return None
    return meta


@router.get("/watch", response_model=WatchAppInfo)
def watch_app_info() -> WatchAppInfo:
    """Name, destination, size and checksums of the published watch app."""
    meta = _meta()
    if meta is None:
        return WatchAppInfo(available=False)
    try:
        return WatchAppInfo(available=True, **meta)
    except (ValueError, TypeError):
        # A file without readable metadata is not offered: installing it means
        # knowing where it goes and what the watch's CRC should be.
        return WatchAppInfo(available=False)


@download_router.api_route("/watch/{file_name}", methods=["GET", "HEAD"])
def download_watch_app(file_name: str) -> FileResponse:
    """The published .uapp, by the name the metadata gives. 404 otherwise."""
    meta = _meta()
    if meta is None or file_name != meta["file_name"]:
        raise HTTPException(status_code=404, detail="No such watch app in this build")
    return FileResponse(
        settings.watch_apps_dir / file_name,
        media_type="application/octet-stream",
        filename=file_name,
    )
