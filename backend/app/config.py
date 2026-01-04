"""Application configuration."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings


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

    # MQTT
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
            self.db_path = self.data_dir / "helf.json"
        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
