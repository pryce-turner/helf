"""The PreToolUse hook that backs up before a migration.

Worth testing because it is a *safety* mechanism whose failure is silent: when
it does not fire, nothing is wrong until the migration you needed to roll back
is the one with no snapshot behind it. That happened on 2026-08-19 — the
matcher required `alembic` and the verb on the same line, so driving alembic
through its Python API slipped past and a migration reached production with no
backup.

The tests drive the real script with real PreToolUse payloads against a
throwaway database, and assert on whether a backup file appears.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPO_ROOT / "scripts" / "pre-migration-backup.sh"

MUTATING = [
    pytest.param(".venv/bin/alembic upgrade head", id="cli-upgrade"),
    pytest.param(".venv/bin/python -m alembic upgrade head", id="cli-module-upgrade"),
    pytest.param("cd backend && .venv/bin/alembic downgrade -1", id="cli-downgrade"),
    pytest.param(".venv/bin/alembic stamp head", id="cli-stamp"),
    pytest.param(
        '.venv/bin/python - <<PY\n'
        "from alembic import command\n"
        "from alembic.config import Config\n"
        'command.upgrade(Config("alembic.ini"), "head")\n'
        "PY",
        id="python-api-multiline",
    ),
    pytest.param(
        '.venv/bin/python -c "\nfrom alembic import command\n'
        'command.downgrade(cfg, \'base\')\n"',
        id="python-api-c-string",
    ),
]

READ_ONLY = [
    pytest.param(".venv/bin/alembic check", id="check"),
    pytest.param(".venv/bin/python -m alembic current", id="current"),
    pytest.param(".venv/bin/alembic history", id="history"),
    pytest.param("pytest -q", id="unrelated"),
]


def _fire(command_text: str, tmp_path: Path) -> bool:
    """Run the hook against a copy of the schema; did it write a backup?"""
    db = tmp_path / "helf.db"
    shutil.copy(REPO_ROOT / "data" / "helf.db", db)

    payload = json.dumps({"tool_input": {"command": command_text}})
    result = subprocess.run(
        ["bash", str(HOOK)],
        input=payload,
        text=True,
        capture_output=True,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HELF_DB": str(db)},
    )
    assert result.returncode == 0, result.stderr
    return any(tmp_path.glob("helf.db.auto-*.bak"))


@pytest.mark.skipif(
    not (REPO_ROOT / "data" / "helf.db").exists(),
    reason="no database to protect (fresh clone)",
)
class TestPreMigrationHook:
    @pytest.mark.parametrize("command_text", MUTATING)
    def test_a_migration_gets_a_backup(self, command_text, tmp_path):
        """However alembic is invoked. The CLI is not the only way in, and the
        Python API is exactly what you reach for when the console script is
        unusable — a venv built at another path has a dead shebang — which is
        when the hook matters most."""
        assert _fire(command_text, tmp_path) is True

    @pytest.mark.parametrize("command_text", READ_ONLY)
    def test_a_read_does_not(self, command_text, tmp_path):
        """`current`, `check` and `history` are polled often. Backing up on
        every status check would bury the deliberate snapshots in noise."""
        assert _fire(command_text, tmp_path) is False
