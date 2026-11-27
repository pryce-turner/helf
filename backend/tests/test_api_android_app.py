"""The Android app endpoints - what the image carries, and the download."""

import json

import pytest

from app.config import settings

META = {
    "version_name": "1.0",
    "version_code": 1,
    "size_bytes": 11,
    "sha256": "ab" * 32,
    "built_at": "2026-11-26T20:00:00Z",
}


@pytest.fixture()
def android_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "android_dir", tmp_path)
    return tmp_path


def _install(android_dir):
    (android_dir / "helf.apk").write_bytes(b"not an apk!!")
    (android_dir / "helf-apk.json").write_text(json.dumps(META))


def test_info_when_available(client, android_dir):
    _install(android_dir)
    r = client.get("/api/app/android")
    assert r.status_code == 200
    assert r.json() == {"available": True, **META}


def test_info_when_absent(client, android_dir):
    r = client.get("/api/app/android")
    assert r.status_code == 200
    assert r.json() == {
        "available": False,
        "version_name": None,
        "version_code": None,
        "size_bytes": None,
        "sha256": None,
        "built_at": None,
    }


def test_info_unavailable_without_readable_metadata(client, android_dir):
    (android_dir / "helf.apk").write_bytes(b"x")
    (android_dir / "helf-apk.json").write_text("{not json")
    assert client.get("/api/app/android").json()["available"] is False


def test_download_headers(client, android_dir):
    _install(android_dir)
    r = client.get("/download/helf.apk")
    assert r.status_code == 200
    assert r.content == b"not an apk!!"
    assert r.headers["content-type"] == "application/vnd.android.package-archive"
    assert 'attachment; filename="helf.apk"' in r.headers["content-disposition"]


def test_download_answers_head(client, android_dir):
    _install(android_dir)
    r = client.head("/download/helf.apk")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/vnd.android.package-archive"
    assert r.headers["content-length"] == "12"


def test_download_404_when_absent(client, android_dir):
    assert client.get("/download/helf.apk").status_code == 404
