"""The UNA Watch file mirror - plan 0023.

What matters: a file lands only if its bytes match the CRC the watch computed,
a re-upload is a no-op, changed content never overwrites what came before, and
no path can escape the mirror directory.
"""

import json
import zlib

import pytest

from app.config import settings


@pytest.fixture()
def una_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    return tmp_path / "una"


def _put(client, path, data: bytes, mtime="1763800000000000", crc=None, size=None):
    return client.put(
        "/api/watch/files",
        params={"path": path},
        content=data,
        headers={
            "Content-Type": "application/octet-stream",
            "X-Watch-Size": str(len(data) if size is None else size),
            "X-Watch-Mtime": mtime,
            "X-Watch-Crc32": f"{zlib.crc32(data) if crc is None else crc:08x}",
        },
    )


PATH = "/DailyHealth/202611/dh_20261121.json"


def test_upload_then_manifest(client, una_dir):
    body = b'{"dailySteps": 7000}'
    r = _put(client, PATH, body)
    assert r.status_code == 200
    assert r.json() == {"path": PATH, "status": "stored", "stored_as": PATH[1:]}
    assert (una_dir / "files" / PATH[1:]).read_bytes() == body

    files = client.get("/api/watch/files").json()["files"]
    assert len(files) == 1
    assert files[0] | {"received_at": None} == {
        "path": PATH,
        "size": len(body),
        "mtime": "1763800000000000",
        "crc32": zlib.crc32(body),
        "received_at": None,
    }


def test_reupload_is_a_noop(client, una_dir):
    _put(client, PATH, b"{}")
    assert _put(client, PATH, b"{}").json()["status"] == "unchanged"
    lines = (una_dir / "manifest.jsonl").read_text().splitlines()
    assert len(lines) == 1


def test_same_bytes_new_mtime_is_recorded_without_a_second_copy(client, una_dir):
    _put(client, PATH, b"{}")
    r = _put(client, PATH, b"{}", mtime="1763900000000000")
    assert r.json()["status"] == "touched"
    assert client.get("/api/watch/files").json()["files"][0]["mtime"] == "1763900000000000"
    assert len(list((una_dir / "files").rglob("*.json*"))) == 1


def test_changed_content_is_kept_beside_the_original(client, una_dir):
    _put(client, PATH, b'{"v": 1}')
    second = b'{"v": 2}'
    r = _put(client, PATH, second, mtime="1763900000000000")
    assert r.json()["status"] == "stored"
    assert r.json()["stored_as"] == f"{PATH[1:]}.v{zlib.crc32(second):08x}"
    assert (una_dir / "files" / PATH[1:]).read_bytes() == b'{"v": 1}'
    assert client.get("/api/watch/files").json()["files"][0]["crc32"] == zlib.crc32(second)


def test_crc_mismatch_is_refused_and_writes_nothing(client, una_dir):
    r = _put(client, PATH, b"{}", crc=0xDEADBEEF)
    assert r.status_code == 422
    assert "CRC" in r.json()["detail"]
    assert client.get("/api/watch/files").json()["files"] == []


def test_size_mismatch_is_refused(client, una_dir):
    assert _put(client, PATH, b"{}", size=99).status_code == 422


@pytest.mark.parametrize(
    "path",
    ["relative.json", "/a/../../etc/passwd", "/a/./b", "/", "/a\\b", "/dir/"],
)
def test_paths_cannot_escape_the_mirror(client, una_dir, path):
    assert _put(client, path, b"x").status_code == 422
    assert not (una_dir / "files").exists() or not any((una_dir / "files").rglob("*"))


def test_binary_files_survive_byte_for_byte(client, una_dir):
    fit = bytes(range(256)) * 40
    path = "/Apps/Running/Activity/202611/activity_1.fit"
    assert _put(client, path, fit).status_code == 200
    assert (una_dir / "files" / path[1:]).read_bytes() == fit


def test_manifest_is_append_only_json_lines(client, una_dir):
    _put(client, PATH, b"1")
    _put(client, PATH, b"2")
    lines = [json.loads(x) for x in (una_dir / "manifest.jsonl").read_text().splitlines()]
    assert [x["crc32"] for x in lines] == [zlib.crc32(b"1"), zlib.crc32(b"2")]
