#!/usr/bin/env bash
#
# PreToolUse hook: never let a migration run against helf.db without a backup.
#
# AGENTS.md already says to back up before every migration. That is prose, and
# prose is advisory — an agent that skims it runs `alembic upgrade head` against
# live production data with nothing to roll back to. This turns the convention
# into a mechanism.
#
# It *creates* the backup rather than blocking. Blocking teaches a model to work
# around the block; a backup that simply always exists has no failure mode worth
# routing around. Cost is ~3MB and ~200ms per migration.
#
# Reads the PreToolUse JSON payload on stdin; exit 0 allows the tool call.
#
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
payload="$(cat)"

command_text="$(printf '%s' "$payload" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("command", ""))
except Exception:
    print("")
' 2>/dev/null || true)"

# Only migrations. `alembic current`/`check`/`history` are reads and need no
# backup; matching them would back up on every status poll.
if ! printf '%s' "$command_text" | grep -Eq 'alembic[^|;&]*\b(upgrade|downgrade|stamp)\b'; then
    exit 0
fi

db="${HELF_DB:-$repo_root/data/helf.db}"
[[ -f "$db" ]] || exit 0   # nothing to protect (fresh clone, or a test database)

# Skip if one is already fresh: a plan that runs three migrations back to back
# does not need three snapshots of an unchanged database. 10 minutes is long
# enough to cover a migration sequence, short enough that a later session in the
# same day still gets its own.
if [[ -n "$(find "$(dirname "$db")" -maxdepth 1 -name "$(basename "$db").auto-*.bak" -mmin -10 2>/dev/null)" ]]; then
    exit 0
fi

if ! out="$("$repo_root/scripts/backup-db.sh" 2>&1)"; then
    # Fail loud. If we cannot back up, the migration should not be the thing
    # that discovers that. Exit 2 blocks the call and shows stderr to the model.
    echo "pre-migration-backup: could not back up $db — blocking the migration." >&2
    echo "$out" >&2
    exit 2
fi

echo "$out" >&2

# Keep the newest 10 auto-backups. The pre-<label> ones are deliberate and are
# never pruned; these are automatic and would otherwise grow without bound.
find "$(dirname "$db")" -maxdepth 1 -name "$(basename "$db").auto-*.bak" -print0 2>/dev/null \
    | xargs -0 ls -t 2>/dev/null \
    | tail -n +11 \
    | while read -r stale; do rm -f "$stale"; done

exit 0
