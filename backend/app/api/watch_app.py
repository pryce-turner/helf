"""Watch apps built by the image (plans 0024, 0026, 0027): what is published, and the files.

Built by the Dockerfile's `watch-build` stage and copied onto the data volume
by the `helf-watch-app` service (`scripts/publish-watch-app.sh`), one folder
per app: `settings.watch_apps_dir/<Folder>/<File>.uapp` beside its
`watch-app.json`. The phone downloads from here and writes the file to the
watch over Bluetooth (`frontend/src/lib/ftsInstall.ts`). Nothing here builds
anything or talks to the watch.
"""

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import settings
from app.models.watch_app import WatchAppInfo, WatchAppList

# Two routers for the same reason as android_app.py: /download/ is outside
# the service worker's NetworkFirst /api/ route, so the file is never cached.
router = APIRouter()
download_router = APIRouter()

META_FILE = "watch-app.json"
# The installer's own rule for a folder (ftsInstall.ts FOLDER), so Helf never
# offers an app the phone would refuse to write.
FOLDER = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def _meta(folder: Path) -> dict | None:
    """The app in `folder`, if its metadata is readable and names a file beside it."""
    try:
        meta = json.loads((folder / META_FILE).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(meta, dict):
        return None
    name, where = meta.get("file_name"), meta.get("folder")
    if not isinstance(name, str) or not isinstance(where, str):
        return None
    # Only a plain file name: it is joined to a directory below. And the
    # folder it claims must be the one it was found in.
    if "/" in name or "\\" in name or name.startswith(".") or not name.endswith(".uapp"):
        return None
    if where != folder.name or not FOLDER.match(where):
        return None
    if not (folder / name).is_file():
        return None
    return meta


def _apps() -> list[WatchAppInfo]:
    root = settings.watch_apps_dir
    if not root.is_dir():
        return []
    apps = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        meta = _meta(folder)
        if meta is None:
            continue
        try:
            apps.append(WatchAppInfo(available=True, **meta))
        except (ValueError, TypeError):
            # Not offered without readable metadata: installing means knowing
            # where it goes and what the watch's CRC should be.
            continue
    return apps


@router.get("/watch", response_model=WatchAppList)
def watch_apps() -> WatchAppList:
    """Every published watch app: name, destination, size and checksums."""
    return WatchAppList(apps=_apps())


@download_router.api_route("/watch/{folder}/{file_name}", methods=["GET", "HEAD"])
def download_watch_app(folder: str, file_name: str) -> FileResponse:
    """A published .uapp, by the folder and name its metadata gives. 404 otherwise."""
    if not FOLDER.match(folder):
        raise HTTPException(status_code=404, detail="No such watch app in this build")
    meta = _meta(settings.watch_apps_dir / folder)
    if meta is None or file_name != meta["file_name"]:
        raise HTTPException(status_code=404, detail="No such watch app in this build")
    return FileResponse(
        settings.watch_apps_dir / folder / file_name,
        media_type="application/octet-stream",
        filename=file_name,
    )
