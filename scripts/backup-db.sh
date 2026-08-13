#!/usr/bin/env bash
#
# Back up helf.db the only way that is correct while the app is running.
#
# WAL is on, so `cp helf.db` is not a consistent copy: committed pages may still
# be sitting in helf.db-wal, and a plain copy takes the main file without them.
# `.backup` uses SQLite's own online backup API, which walks the database
# through a read transaction and therefore includes the WAL.
#
# Usage:
#   scripts/backup-db.sh pre-0013          # -> data/helf.db.pre-0013.bak
#   scripts/backup-db.sh                   # -> data/helf.db.auto-<stamp>.bak
#
# Env:
#   HELF_DB   path to the database   (default: data/helf.db, repo-relative)
#
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
db="${HELF_DB:-$repo_root/data/helf.db}"

if [[ ! -f "$db" ]]; then
    echo "backup-db: no database at $db" >&2
    exit 1
fi

label="${1:-auto-$(date +%Y%m%d-%H%M%S)}"
dest="$db.$label.bak"

if [[ -e "$dest" ]]; then
    echo "backup-db: $dest already exists — refusing to overwrite a backup" >&2
    exit 1
fi

# `.backup` rather than `cp`: see the header. Quoting matters — the path is
# interpreted by sqlite3's dot-command parser, not by the shell.
sqlite3 "$db" ".backup '$dest'"

# Verify through an `immutable=1` handle, never a plain path. The destination
# inherits journal_mode=WAL, so opening it read-write would create
# helf.db.<label>.bak-wal / -shm beside it — sidecars that make the backup look
# like a live database and invite exactly the partial `cp` this script exists to
# prevent. `.backup` leaves a fully checkpointed file, so immutable is accurate.
ro="file:$dest?immutable=1"

# A backup that is silently corrupt is worse than none, because it is trusted.
# integrity_check reads every page; on a database this size it costs ~50ms.
check="$(sqlite3 "$ro" 'PRAGMA integrity_check;')"
if [[ "$check" != "ok" ]]; then
    echo "backup-db: integrity check FAILED on $dest:" >&2
    echo "$check" >&2
    exit 1
fi

# Row counts, not just "it exists" — the repo's commit convention asks for
# counts and checksums against the real database rather than "tests pass".
read -r workouts observations metrics <<<"$(sqlite3 "$ro" \
    "SELECT (SELECT count(*) FROM workouts),
            (SELECT count(*) FROM observation),
            (SELECT count(*) FROM metric);" | tr '|' ' ')"

printf 'backup-db: %s\n' "$dest"
printf '  integrity ok · %s · workouts=%s observation=%s metric=%s · rev=%s\n' \
    "$(du -h "$dest" | cut -f1)" "$workouts" "$observations" "$metrics" \
    "$(sqlite3 "$ro" 'SELECT version_num FROM alembic_version;' 2>/dev/null || echo '?')"
