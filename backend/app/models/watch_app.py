"""Watch app data models: what the install button needs to know (plan 0026)."""

from pydantic import BaseModel


class WatchAppInfo(BaseModel):
    """The watch app the image was built with, or `available: false` without one.

    Nulls rather than a 404 when there is none, as for the APK: a development
    checkout has none, and absence is an answer, not an error.

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
