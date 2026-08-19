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

# Newlines are flattened *first*. `grep` matches within a line, and the previous
# pattern required `alembic` and the verb on one — so it caught
# `alembic upgrade head` and missed this, which is how a migration reached
# production untouched on 2026-08-19:
#
#     python - <<PY
#     from alembic import command      <- "alembic" here
#     command.upgrade(cfg, "head")     <- "upgrade" on another line
#     PY
#
# The Python API is not an exotic way to run a migration; it is what you reach
# for the moment the console script is unusable (a venv built at a different
# path has a dead shebang), which is exactly when the hook matters most.
flat="$(printf '%s' "$command_text" | tr '\n\r\t' '   ')"

# Two independent signals rather than one pattern: does this involve alembic at
# all, and does it name a verb that changes the schema. `current`, `check`,
# `history` and `heads` carry no verb and so still cost nothing.
#
# **Deliberately biased toward false positives.** Backing up because someone
# grepped a migration file for the word "upgrade" costs 3MB and 200ms, at most
# once per 10 minutes. Missing a real migration costs the database. Anything
# that reaches alembic without naming it — a Makefile target, a shell alias —
# is still invisible here; that is the remaining hole, and it is why AGENTS.md
# keeps saying to back up by hand before anything unusual.
if ! printf '%s' "$flat" | grep -Eqi 'alembic'; then
    exit 0
fi
if ! printf '%s' "$flat" | grep -Eq '\b(upgrade|downgrade|stamp)\b'; then
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

# Nothing is pruned. This used to keep only the newest 10 auto-backups, which
# contradicts the retention policy in AGENTS.md ("Backups, and why none are
# deleted"): at ~3MB each the entire history is cheaper than one bad restore,
# and the snapshot a cap discards is the one you turn out to need. The 10-minute
# freshness check above is what keeps a back-to-back migration sequence from
# writing a snapshot per step, so growth is per-session, not per-command.

exit 0
