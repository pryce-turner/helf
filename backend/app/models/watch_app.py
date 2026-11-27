"""Watch app data models: what the install buttons need to know (plans 0026, 0027)."""

from pydantic import BaseModel


class WatchAppInfo(BaseModel):
    """One watch app the image was built with.

    `folder` and `file_name` are where it goes on the watch
    (`/Apps/<folder>/<file_name>`); the installer is scoped to that folder.
    `crc32` is the same CRC-32 the watch's DIGEST computes, as 8 hex digits,
    which is how the phone checks the watch's copy without reading it back.
    """

    available: bool
    name: str | None = None
    folder: str | None = None
    file_name: str | None = None
    app_id: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    crc32: str | None = None
    sdk_commit: str | None = None
    toolchain: str | None = None
    built_at: str | None = None


class WatchAppList(BaseModel):
    """Every published watch app. Empty, not a 404, in a checkout without any."""

    apps: list[WatchAppInfo]
