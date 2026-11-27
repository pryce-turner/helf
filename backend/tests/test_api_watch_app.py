"""The watch app endpoints (plans 0026, 0027): what is published, and the downloads."""

import json

import pytest

from app.config import settings

SLEEP = {
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
DRINKS = {**SLEEP, "name": "Drinks", "folder": "Drinks", "file_name": "Drinks.uapp", "app_id": "0C96179DF5834759"}


@pytest.fixture()
def apps_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "watch_apps_dir", tmp_path)
    return tmp_path


def _publish(apps_dir, meta, folder=None, body=b"UAPP-ish...."):
    d = apps_dir / (folder or meta["folder"])
    d.mkdir(exist_ok=True)
    # Under its base name, so a hostile file_name still has a file to find.
    (d / meta["file_name"].replace("\\", "/").split("/")[-1]).write_bytes(body)
    (d / "watch-app.json").write_text(json.dumps(meta))


def test_lists_every_published_app(client, apps_dir):
    _publish(apps_dir, SLEEP)
    _publish(apps_dir, DRINKS)
    r = client.get("/api/app/watch")
    assert r.status_code == 200
    assert r.json() == {"apps": [{"available": True, **DRINKS}, {"available": True, **SLEEP}]}


def test_empty_when_nothing_published(client, apps_dir):
    assert client.get("/api/app/watch").json() == {"apps": []}


def test_empty_when_the_directory_is_missing(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "watch_apps_dir", tmp_path / "nope")
    assert client.get("/api/app/watch").json() == {"apps": []}


def test_ignores_the_single_app_layout_of_c046cb8(client, apps_dir):
    # The first publish put SleepLog.uapp and watch-app.json at the top level.
    (apps_dir / "SleepLog.uapp").write_bytes(b"x")
    (apps_dir / "watch-app.json").write_text(json.dumps(SLEEP))
    assert client.get("/api/app/watch").json() == {"apps": []}


def test_skips_unreadable_or_incomplete_apps(client, apps_dir):
    _publish(apps_dir, DRINKS)
    (apps_dir / "Broken").mkdir()
    (apps_dir / "Broken" / "watch-app.json").write_text("{not json")
    (apps_dir / "SleepLog").mkdir()
    (apps_dir / "SleepLog" / "watch-app.json").write_text(json.dumps(SLEEP))   # no .uapp
    assert [a["folder"] for a in client.get("/api/app/watch").json()["apps"]] == ["Drinks"]


@pytest.mark.parametrize(
    "meta",
    [
        {**SLEEP, "file_name": "../helf.db"},
        {**SLEEP, "file_name": "sub/SleepLog.uapp"},
        {**SLEEP, "file_name": ".hidden.uapp"},
        {**SLEEP, "file_name": "SleepLog.bin"},
        {**SLEEP, "folder": "Drinks"},   # claims a folder it is not in
    ],
)
def test_metadata_cannot_point_elsewhere(client, apps_dir, meta):
    _publish(apps_dir, meta, folder="SleepLog")
    assert client.get("/api/app/watch").json() == {"apps": []}


def test_download(client, apps_dir):
    _publish(apps_dir, SLEEP)
    r = client.get("/download/watch/SleepLog/SleepLog.uapp")
    assert r.status_code == 200
    assert r.content == b"UAPP-ish...."
    assert r.headers["content-type"] == "application/octet-stream"
    assert 'filename="SleepLog.uapp"' in r.headers["content-disposition"]
    assert client.head("/download/watch/SleepLog/SleepLog.uapp").headers["content-length"] == "12"


def test_download_only_the_published_name(client, apps_dir):
    _publish(apps_dir, SLEEP)
    (apps_dir / "SleepLog" / "other.uapp").write_bytes(b"x")
    for path in [
        "/download/watch/SleepLog/other.uapp",
        "/download/watch/SleepLog/watch-app.json",
        "/download/watch/Drinks/SleepLog.uapp",
        "/download/watch/..%2FSleepLog/SleepLog.uapp",
    ]:
        assert client.get(path).status_code == 404, path


def test_download_404_when_absent(client, apps_dir):
    assert client.get("/download/watch/SleepLog/SleepLog.uapp").status_code == 404
