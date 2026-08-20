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
        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
