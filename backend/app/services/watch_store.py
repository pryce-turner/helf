"""A verified, append-only mirror of files read off the UNA Watch (plan 0023).

Raw files, not rows. The watch's daily-health JSON is still changing upstream
(a time-stamped HR series is planned) and its `.fit` workouts are binary, so
neither belongs in `document.raw` (JSON-only) or in `metric` until a promotion
step is designed against real files. Keeping the bytes exactly as the watch
wrote them means that step is a re-run over this directory, never a re-read of
a watch that may have rotated the file away.

Layout under ``<data_dir>/una/``:

- ``files/<watch path>`` — the first content received for that path.
- ``files/<watch path>.v<crc32>`` — any later, different content. Nothing is
  overwritten, matching the rule for everything else in ``data/``.
- ``manifest.jsonl`` — one line per accepted upload, append-only. The current
  state of a path is its last line. This is what the phone diffs against, so
  the phone itself remembers nothing (plan 0015 §4's rule).
"""

from __future__ import annotations

import fcntl
import json
import os
import posixpath
import zlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings

MAX_FILE_BYTES = 32 * 1024 * 1024


class WatchFileRejected(ValueError):
    """The upload is malformed or does not match what it claims to be."""


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    size: int
    mtime: str
    crc32: int
    stored_as: str
    received_at: str


def _root() -> Path:
    # Read at call time, not import time, so tests can point it elsewhere.
    return Path(settings.data_dir) / "una"


def normalise_path(path: str) -> str:
    """The watch path, or a rejection. Never lets a path leave ``files/``."""
    if not path.startswith("/") or "\x00" in path or "\\" in path:
        raise WatchFileRejected(f"not an absolute watch path: {path!r}")
    parts = path.split("/")
    if any(p in {"..", "."} for p in parts):
        raise WatchFileRejected(f"path traversal: {path!r}")
    clean = posixpath.normpath(path)
    if clean == "/" or clean != path:
        raise WatchFileRejected(f"not a file path: {path!r}")
    return clean


def current() -> dict[str, ManifestEntry]:
    """The last manifest line for every path."""
    manifest = _root() / "manifest.jsonl"
    latest: dict[str, ManifestEntry] = {}
    if not manifest.exists():
        return latest
    with manifest.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            entry = ManifestEntry(**json.loads(line))
            latest[entry.path] = entry
    return latest


def store(path: str, data: bytes, *, size: int, mtime: str, crc32: int) -> tuple[str, ManifestEntry]:
    """Verify and keep one file. Returns (outcome, entry).

    ``outcome`` is ``stored`` (new content), ``touched`` (same bytes, new
    mtime — recorded so the phone stops re-fetching it) or ``unchanged``.

    The CRC is checked again here, against the bytes that crossed HTTP. The
    phone already compared the watch's DIGEST with what it read over BLE; this
    closes the last hop, so what lands on disk is what the watch hashed.
    """
    path = normalise_path(path)
    if not mtime.isdigit():
        raise WatchFileRejected(f"mtime must be a decimal integer, got {mtime!r}")
    if len(data) != size:
        raise WatchFileRejected(f"size mismatch: header says {size}, body is {len(data)}")
    actual = zlib.crc32(data) & 0xFFFFFFFF
    if actual != crc32:
        raise WatchFileRejected(f"CRC mismatch: header says {crc32:08x}, body is {actual:08x}")

    root = _root()
    files = root / "files"
    files.mkdir(parents=True, exist_ok=True)
    manifest = root / "manifest.jsonl"

    # One writer at a time across uvicorn workers: the lock covers the
    # read-decide-write, so two uploads of one path cannot both "store".
    with (root / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            held = current().get(path)
            if held and held.crc32 == crc32 and held.size == size:
                if held.mtime == mtime:
                    return "unchanged", held
                outcome, stored_as = "touched", held.stored_as
            else:
                outcome = "stored"
                stored_as = path.lstrip("/")
                if (files / stored_as).exists():
                    stored_as = f"{stored_as}.v{crc32:08x}"
                target = files / stored_as
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    tmp = target.with_name(target.name + ".part")
                    tmp.write_bytes(data)
                    os.replace(tmp, target)

            entry = ManifestEntry(
                path=path,
                size=size,
                mtime=mtime,
                crc32=crc32,
                stored_as=stored_as,
                received_at=datetime.now(UTC).isoformat(timespec="seconds"),
            )
            with manifest.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(entry)) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            return outcome, entry
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
