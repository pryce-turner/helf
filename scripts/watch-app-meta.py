#!/usr/bin/env python3
"""Describe a built watch app for Helf (plans 0026, 0027). Used by the Dockerfile.

    watch-app-meta.py <CMakeLists.txt> <built .uapp> <out root> <sdk commit> <toolchain>

Copies the .uapp to <out root>/<APP_FILE_NAME>/<APP_FILE_NAME>.uapp, the
folder and fixed name the installer writes on the watch (the build names it
with its version), and writes watch-app.json beside it. The app's identity
comes from its own CMakeLists.txt, so there is one place it is set.

`crc32` is zlib's, the same CRC-32 as the watch's DIGEST, so the phone can
check the watch's copy without reading it back.
"""

import hashlib
import json
import re
import shutil
import sys
import zlib
from pathlib import Path


def cmake_set(text: str, name: str) -> str:
    m = re.search(rf'^\s*set\({name}\s+"([^"]*)"\)', text, re.MULTILINE)
    if not m:
        sys.exit(f"watch-app-meta: {name} is not set in CMakeLists.txt")
    return m.group(1)


def main() -> None:
    cmakelists, built, out, sdk_commit, toolchain = sys.argv[1:6]
    text = Path(cmakelists).read_text()
    file_stem = cmake_set(text, "APP_FILE_NAME")
    app_id = cmake_set(text, "APP_ID")
    data = Path(built).read_bytes()
    # MainHeader (kernel AppHeaders.hpp): uappID u64, uappVersion u32,
    # libcVersion u32, serviceSize u32, flags u32, all little-endian.
    if len(data) < 24 or int.from_bytes(data[0:8], "little") != int(app_id, 16):
        sys.exit(f"watch-app-meta: {built} does not carry APP_ID {app_id}")
    # The packed autostart flag must say what CMakeLists.txt asked for: an
    # app meant to start at boot (Sleep Log) that does not would never run.
    flags = int.from_bytes(data[20:24], "little")
    m = re.search(r"^\s*set\(APP_AUTOSTART\s+(\w+)\)", text, re.MULTILINE)
    want_autostart = bool(m) and m.group(1).upper() in {"ON", "TRUE", "1", "YES"}
    if bool(flags & 0x08) != want_autostart:
        sys.exit(f"watch-app-meta: FLAG_APP_AUTO_START is {bool(flags & 0x08)}, CMakeLists.txt says {want_autostart}")

    out_dir = Path(out) / file_stem
    out_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{file_stem}.uapp"
    shutil.copyfile(built, out_dir / file_name)
    meta = {
        "name": cmake_set(text, "APP_USER_NAME"),
        # The folder on the watch is the file's stem: /Apps/SleepLog/SleepLog.uapp.
        "folder": file_stem,
        "file_name": file_name,
        "app_id": app_id,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "crc32": f"{zlib.crc32(data) & 0xFFFFFFFF:08x}",
        "sdk_commit": sdk_commit,
        "toolchain": toolchain,
    }
    (out_dir / "watch-app.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
