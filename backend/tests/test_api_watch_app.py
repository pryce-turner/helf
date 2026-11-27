"""The watch app endpoints (plan 0026): what is published, and the download."""

import json

import pytest

from app.config import settings

META = {
    "name": "Sleep Log",
    "folder": "SleepLog",
    "file_name": "SleepLog.uapp",
    "app_id": "64313DF28C1B15C8",
    "size_bytes": 12,
    "sha256": "ab" * 32,
    "crc32": "0123abcd",
    "sdk_commit": "f" * 40,
    "toolchain": "15.2.rel1",
    "built_at": "2026-11-27T05:00:00Z",
}


@pytest.fixture()
def apps_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "watch_apps_dir", tmp_path)
    return tmp_path


def _publish(apps_dir, meta=META):
    (apps_dir / "SleepLog.uapp").write_bytes(b"UAPP-ish....")
    (apps_dir / "watch-app.json").write_text(json.dumps(meta))


def test_info_when_available(client, apps_dir):
    _publish(apps_dir)
    r = client.get("/api/app/watch")
    assert r.status_code == 200
    assert r.json() == {"available": True, **META}


def test_info_when_absent(client, apps_dir):
    r = client.get("/api/app/watch")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert all(v is None for k, v in body.items() if k != "available")


def test_info_unavailable_without_readable_metadata(client, apps_dir):
    (apps_dir / "SleepLog.uapp").write_bytes(b"x")
    (apps_dir / "watch-app.json").write_text("{not json")
    assert client.get("/api/app/watch").json()["available"] is False


def test_info_unavailable_when_the_file_is_missing(client, apps_dir):
    (apps_dir / "watch-app.json").write_text(json.dumps(META))
    assert client.get("/api/app/watch").json()["available"] is False


@pytest.mark.parametrize("name", ["../helf.db", "sub/SleepLog.uapp", ".hidden.uapp", "SleepLog.bin"])
def test_metadata_cannot_point_outside_the_directory(client, apps_dir, name):
    _publish(apps_dir, {**META, "file_name": name})
    assert client.get("/api/app/watch").json()["available"] is False


def test_download(client, apps_dir):
    _publish(apps_dir)
    r = client.get("/download/watch/SleepLog.uapp")
    assert r.status_code == 200
    assert r.content == b"UAPP-ish...."
    assert r.headers["content-type"] == "application/octet-stream"
    assert 'filename="SleepLog.uapp"' in r.headers["content-disposition"]
    assert client.head("/download/watch/SleepLog.uapp").headers["content-length"] == "12"


def test_download_only_the_published_name(client, apps_dir):
    _publish(apps_dir)
    (apps_dir / "other.uapp").write_bytes(b"x")
    assert client.get("/download/watch/other.uapp").status_code == 404
    assert client.get("/download/watch/watch-app.json").status_code == 404


def test_download_404_when_absent(client, apps_dir):
    assert client.get("/download/watch/SleepLog.uapp").status_code == 404
