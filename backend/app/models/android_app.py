"""Android app data models — what the download prompt needs to know."""

from pydantic import BaseModel


class AndroidAppInfo(BaseModel):
    """The APK the image was built with, or `available: false` without one.

    Nulls rather than a 404 when there is no APK: a development checkout has
    none, and the page asks this on every load to decide whether to offer a
    download. Absence is an answer, not an error.
    """

    available: bool
    version_name: str | None = None
    version_code: int | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    built_at: str | None = None
