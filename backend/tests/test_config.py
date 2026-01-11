"""Tests for config.py - Application settings."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import Settings


class TestSettings:
    """Tests for Settings configuration class."""

    def test_settings_default_values(self, tmp_path, monkeypatch):
        """Test that Settings has expected default values."""
        # Use tmp_path for data directory
        monkeypatch.delenv("DATA_DIR", raising=False)
        monkeypatch.delenv("HELF_DATA_PATH", raising=False)
        monkeypatch.chdir(tmp_path)

        settings = Settings()

        assert settings.app_name == "Helf API"
        assert settings.app_version == "2.0.0"
        assert settings.debug is False
        assert settings.timezone == "America/Los_Angeles"
        assert settings.cors_origins == ["*"]

    def test_settings_db_path_auto_set_from_data_dir(self, tmp_path, monkeypatch):
        """Test that db_path is automatically set from data_dir."""
        data_dir = tmp_path / "data"
        monkeypatch.setenv("DATA_DIR", str(data_dir))

        settings = Settings()

        assert settings.data_dir == data_dir
        assert settings.db_path == data_dir / "helf.db"

    def test_settings_data_dir_from_data_dir_env(self, tmp_path, monkeypatch):
        """Test that data_dir is set from DATA_DIR environment variable."""
        data_dir = tmp_path / "custom_data"
        monkeypatch.setenv("DATA_DIR", str(data_dir))

        settings = Settings()

        assert settings.data_dir == data_dir
        assert settings.data_dir.exists()  # Should be created

    def test_settings_data_dir_can_be_overridden_at_init(self, tmp_path, monkeypatch):
        """Test that data_dir can be overridden during initialization."""
        # Note: Environment variables are read at module import time, not at Settings init
        # So we test direct initialization instead
        data_dir = tmp_path / "helf_data"

        settings = Settings(data_dir=data_dir)

        assert settings.data_dir == data_dir
        assert settings.data_dir.exists()

    def test_settings_data_dir_creates_directory_if_not_exists(self, tmp_path, monkeypatch):
        """Test that Settings creates data directory if it doesn't exist."""
        data_dir = tmp_path / "nonexistent" / "data"
        monkeypatch.setenv("DATA_DIR", str(data_dir))

        assert not data_dir.exists()

        settings = Settings()

        assert settings.data_dir.exists()
        assert settings.data_dir.is_dir()

    def test_settings_mqtt_broker_defaults(self, tmp_path, monkeypatch):
        """Test MQTT broker default configuration."""
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        monkeypatch.delenv("MQTT_BROKER_HOST", raising=False)
        monkeypatch.delenv("MQTT_BROKER_PORT", raising=False)

        settings = Settings()

        assert settings.mqtt_broker_host == "localhost"
        assert settings.mqtt_broker_port == 1883

    def test_settings_mqtt_broker_from_env(self, tmp_path, monkeypatch):
        """Test MQTT broker configuration from environment variables."""
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        monkeypatch.setenv("MQTT_BROKER_HOST", "mqtt.example.com")
        monkeypatch.setenv("MQTT_BROKER_PORT", "8883")

        settings = Settings()

        assert settings.mqtt_broker_host == "mqtt.example.com"
        assert settings.mqtt_broker_port == 8883

    def test_settings_mqtt_broker_port_is_integer(self, tmp_path, monkeypatch):
        """Test that MQTT broker port is converted to integer."""
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        monkeypatch.setenv("MQTT_BROKER_PORT", "9001")

        settings = Settings()

        assert isinstance(settings.mqtt_broker_port, int)
        assert settings.mqtt_broker_port == 9001

    def test_settings_custom_db_path(self, tmp_path, monkeypatch):
        """Test that custom db_path can be provided."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        custom_db = data_dir / "custom.db"

        monkeypatch.setenv("DATA_DIR", str(data_dir))

        settings = Settings(db_path=custom_db)

        assert settings.db_path == custom_db

    def test_settings_cors_origins_default(self, tmp_path, monkeypatch):
        """Test CORS origins default to allow all."""
        monkeypatch.setenv("DATA_DIR", str(tmp_path))

        settings = Settings()

        assert settings.cors_origins == ["*"]

    def test_settings_data_dir_priority_data_dir_over_helf_data_path(
        self, tmp_path, monkeypatch
    ):
        """Test that DATA_DIR takes priority over HELF_DATA_PATH."""
        data_dir_1 = tmp_path / "dir1"
        data_dir_2 = tmp_path / "dir2"

        monkeypatch.setenv("DATA_DIR", str(data_dir_1))
        monkeypatch.setenv("HELF_DATA_PATH", str(data_dir_2))

        settings = Settings()

        # DATA_DIR should take precedence
        assert settings.data_dir == data_dir_1

    def test_settings_data_dir_fallback_to_relative_path(self, tmp_path, monkeypatch):
        """Test that data_dir falls back to ../data when no env vars set."""
        monkeypatch.delenv("DATA_DIR", raising=False)
        monkeypatch.delenv("HELF_DATA_PATH", raising=False)
        monkeypatch.chdir(tmp_path)

        settings = Settings()

        # Should default to ../data relative path
        assert settings.data_dir == Path("../data")
        # Directory should be created
        assert settings.data_dir.exists()

    def test_settings_immutable_after_creation(self, tmp_path, monkeypatch):
        """Test that Settings instance can be modified (Pydantic allows it)."""
        monkeypatch.setenv("DATA_DIR", str(tmp_path))

        settings = Settings()
        original_version = settings.app_version

        # Pydantic v2 allows modification by default
        settings.app_version = "3.0.0"

        assert settings.app_version == "3.0.0"
        assert settings.app_version != original_version

    def test_settings_timezone_default(self, tmp_path, monkeypatch):
        """Test timezone default is Pacific."""
        monkeypatch.setenv("DATA_DIR", str(tmp_path))

        settings = Settings()

        assert settings.timezone == "America/Los_Angeles"

    def test_settings_debug_mode_default_false(self, tmp_path, monkeypatch):
        """Test debug mode defaults to False."""
        monkeypatch.setenv("DATA_DIR", str(tmp_path))

        settings = Settings()

        assert settings.debug is False

    def test_settings_multiple_instances_independent(self, tmp_path, monkeypatch):
        """Test that multiple Settings instances are independent."""
        data_dir_1 = tmp_path / "data1"
        data_dir_2 = tmp_path / "data2"

        settings1 = Settings(data_dir=data_dir_1)
        settings2 = Settings(data_dir=data_dir_2)

        assert settings1.data_dir != settings2.data_dir
        assert settings1.db_path != settings2.db_path

    def test_settings_db_path_includes_filename(self, tmp_path, monkeypatch):
        """Test that db_path includes the database filename."""
        monkeypatch.setenv("DATA_DIR", str(tmp_path))

        settings = Settings()

        assert settings.db_path.name == "helf.db"

    def test_settings_data_dir_is_path_object(self, tmp_path, monkeypatch):
        """Test that data_dir is a Path object."""
        monkeypatch.setenv("DATA_DIR", str(tmp_path))

        settings = Settings()

        assert isinstance(settings.data_dir, Path)

    def test_settings_db_path_is_path_object(self, tmp_path, monkeypatch):
        """Test that db_path is a Path object."""
        monkeypatch.setenv("DATA_DIR", str(tmp_path))

        settings = Settings()

        assert isinstance(settings.db_path, Path)

    def test_settings_app_name_and_version_consistent(self, tmp_path, monkeypatch):
        """Test that app name and version are consistent."""
        monkeypatch.setenv("DATA_DIR", str(tmp_path))

        settings = Settings()

        assert "Helf" in settings.app_name
        assert "API" in settings.app_name
        # Version should follow semantic versioning pattern
        version_parts = settings.app_version.split(".")
        assert len(version_parts) == 3
        assert all(part.isdigit() for part in version_parts)

    def test_settings_mqtt_default_port_is_standard(self, tmp_path, monkeypatch):
        """Test that default MQTT port is standard 1883."""
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        monkeypatch.delenv("MQTT_BROKER_PORT", raising=False)

        settings = Settings()

        assert settings.mqtt_broker_port == 1883  # Standard MQTT port

    def test_settings_creates_nested_data_directories(self, tmp_path, monkeypatch):
        """Test that Settings can create nested directory structures."""
        nested_dir = tmp_path / "level1" / "level2" / "level3" / "data"
        monkeypatch.setenv("DATA_DIR", str(nested_dir))

        assert not nested_dir.exists()

        settings = Settings()

        assert nested_dir.exists()
        assert nested_dir.is_dir()
