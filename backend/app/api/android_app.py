"""The Android app: what is built into the image, and the file itself.

The APK is built by the Dockerfile's `android-build` stage and signed onto the
data volume by the `helf-apk` service (`scripts/sign-apk.sh`, plan 0025), into
`settings.android_dir`. Nothing here builds or signs anything.
"""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import settings
from app.models.android_app import AndroidAppInfo

# Two routers because the download is deliberately not under /api/. The service
# worker's /api/ route is NetworkFirst and would cache a 4.6 MB file; /download/
# is left alone by it (and denied navigation fallback in vite.config.ts).
router = APIRouter()
download_router = APIRouter()

APK_MEDIA_TYPE = "application/vnd.android.package-archive"


@router.get("/android", response_model=AndroidAppInfo)
def android_app_info() -> AndroidAppInfo:
    """Version, size and checksum of the bundled APK."""
    apk = settings.android_dir / "helf.apk"
    meta = settings.android_dir / "helf-apk.json"
    if not apk.is_file() or not meta.is_file():
        return AndroidAppInfo(available=False)
    try:
        return AndroidAppInfo(available=True, **json.loads(meta.read_text()))
    except (ValueError, TypeError):
        # An APK without readable metadata is not offered: the prompt shows a
        # version and size, and guessing them would be worse than saying no.
        return AndroidAppInfo(available=False)


# HEAD too: download managers and `curl -I` ask before they fetch.
@download_router.api_route("/helf.apk", methods=["GET", "HEAD"])
def download_apk() -> FileResponse:
    """The APK as an attachment. 404 when the image was built without one."""
    apk = settings.android_dir / "helf.apk"
    if not apk.is_file():
        raise HTTPException(status_code=404, detail="No Android app in this build")
    return FileResponse(apk, media_type=APK_MEDIA_TYPE, filename="helf.apk")
