"""Application configuration."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    # Application
    app_name: str = "Helf API"
    app_version: str = "2.0.0"
    debug: bool = False

    # Paths - DATA_DIR for container, HELF_DATA_PATH for dev, fallback to ../data
    data_dir: Path = Path(os.getenv("DATA_DIR") or os.getenv("HELF_DATA_PATH") or "../data")

    # The Android APK and its helf-apk.json, written onto the data volume by
    # the `helf-apk` service (scripts/sign-apk.sh). Absent until it has run, and
    # in a development checkout, which the app handles (`available: false`).
    # Defaults to <data_dir>/android in __init__; the ANDROID_DIR env var overrides.
    android_dir: Path | None = None

    # Watch apps built into the image and published onto the data volume by
    # the `helf-watch-app` service (scripts/publish-watch-app.sh, plan 0026):
    # the .uapp and its watch-app.json. Absent until it has run, which the app
    # handles (`available: false`). Defaults to <data_dir>/watch-apps; the
    # WATCH_APPS_DIR env var overrides.
    watch_apps_dir: Path | None = None

    # Database
    db_path: Path | None = None

    # MQTT — **off by default** since plan 0015.
    #
    # The BF720 is read straight from the browser over Web Bluetooth, so the
    # phone, the openScale app and the broker are no longer in the path. The
    # code stays because it is the fallback for scales the browser cannot read:
    # `app/lib/bcs.ts` decodes the Bluetooth SIG Body Composition Service and
    # nothing else, while openScale has drivers for around a hundred scales,
    # most of them proprietary. Swap the scale for one of those and this is the
    # way back in.
    #
    # Default False rather than "connect and fail quietly": it used to log
    # `Failed to start MQTT service: Connection refused` on every boot once the
    # broker went away, which is noise that trains you to ignore startup errors.
    mqtt_enabled: bool = os.getenv("MQTT_ENABLED", "").lower() in {"1", "true", "yes"}
    mqtt_broker_host: str = os.getenv("MQTT_BROKER_HOST", "localhost")
    mqtt_broker_port: int = int(os.getenv("MQTT_BROKER_PORT", "1883"))

    # CORS
    cors_origins: list[str] = ["*"]

    # Timezone
    timezone: str = "America/Los_Angeles"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Set db_path if not provided
        if self.db_path is None:
            self.db_path = self.data_dir / "helf.db"
        if self.android_dir is None:
            self.android_dir = self.data_dir / "android"
        if self.watch_apps_dir is None:
            self.watch_apps_dir = self.data_dir / "watch-apps"
        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
