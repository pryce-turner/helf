# Plan 0002: Schema foundation

**Status:** Proposed
**Prerequisites:** none
**Blocks:** every other plan
**Related:** ADR-0002, ADR-0004

Adds the two things the codebase is missing that make all subsequent schema work
possible: a migration framework, and correct SQLite pragmas.

No user-visible change. No data change.

> **Develop against `data/helf.db`.** That file is a copy of production and is
> the path bind-mounted into the container, so migrations are written and tested
> against real data and real row counts — not a synthetic fixture. Current
> profile: 9,292 `workouts`, 150 `body_composition`, 173 `exercises`, 30
> `upcoming_workouts`, 10 `categories`.
>
> Because it is the mounted path, **it is also live data.** Take the `.backup`
> copy in §4 before running anything, every time.

---

## 1. Adopt Alembic

### Why

`backend/app/database.py:27-31` builds schema with
`Base.metadata.create_all(bind=engine)`. It creates missing tables and does
nothing else — no `ALTER`, no column addition, no constraint change. Against a
database with data in it, every schema change in this roadmap is currently
impossible.

`backend/migrations/tinydb_to_sqlite.py` is a one-shot import script, not a
migration framework — it doesn't version anything.

### Steps

1. Add the dependency to `backend/pyproject.toml`:

   ```toml
   dependencies = [
       # ...
       "alembic>=1.14.0",
   ]
   ```

2. Initialise in `backend/`, so migrations sit beside the existing one-shot
   script:

   ```bash
   cd backend && alembic init migrations/alembic
   ```

3. Point `migrations/alembic/env.py` at the app's metadata and settings rather
   than the generated `alembic.ini` URL — the DB path is already configurable
   via `HELF_DATA_PATH` (`app/config.py`) and must not be duplicated:

   ```python
   from app.config import settings
   from app.database import Base
   from app.db import models  # noqa: F401 — registers tables on Base.metadata

   target_metadata = Base.metadata
   config.set_main_option("sqlalchemy.url", f"sqlite:///{settings.db_path}")
   ```

4. **Enable batch mode.** SQLite cannot `ALTER TABLE` in most of the ways the
   later plans need (dropping a column, changing a constraint). Alembic emulates
   it by rebuilding the table, but only if asked — in `env.py`'s
   `context.configure(...)`, both online and offline:

   ```python
   render_as_batch=True,
   ```

   Without this, Plan 0003's `weight_unit` drop fails outright.

5. **Baseline the existing schema.** Autogenerate against a database that
   already matches the models, so revision 1 is an empty no-op that records the
   current state as the starting point:

   ```bash
   alembic revision --autogenerate -m "baseline existing schema"
   ```

   Inspect the generated file. It **must** be empty of operations. If it
   contains any, the models and the live DB have already drifted — resolve that
   before proceeding, because a non-empty baseline will try to re-create tables
   that exist.

6. **Switch startup from `create_all` to Alembic.** In `app/database.py`,
   `init_db()` keeps its name and call site but changes behaviour:

   ```python
   def init_db():
       """Bring the database up to the latest migration."""
       from alembic import command
       from alembic.config import Config

       cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
       command.upgrade(cfg, "head")
   ```

   Keep `create_all()` available for the test suite — `backend/tests/conftest.py`
   builds a fresh schema per run and should not pay migration cost. This is a
   deliberate divergence: tests verify the models, migrations verify the path
   from the old schema to the new. Both need testing, differently (§4).

### Rollback

`alembic downgrade -1`, or restore the pre-migration file copy. Reverting the
code change alone is safe — `create_all()` is a no-op on an existing schema.

---

## 2. Set pragmas on every connection

### Why

No `PRAGMA` is issued anywhere in `backend/app/`. Two live problems:

**Foreign keys are not enforced.** SQLite defaults `foreign_keys` to OFF, per
connection. Every `ForeignKey` in `db/models.py` is currently inert. There may
already be `workouts` rows pointing at deleted exercises.

**Rollback journal mode** takes a database-wide write lock. ADR-0002 and ADR-0004
introduce a second process on this file; without WAL, agent reads and PWA writes
will collide with `database is locked`.

### Check for existing violations first — **done, clean**

```bash
sqlite3 data/helf.db "PRAGMA foreign_key_check;"
```

**Returns empty against the production copy.** No orphaned rows across 9,292
workouts, 30 upcoming, and 150 body-composition rows, despite foreign keys never
having been enforced. Risk R2 in `plans/0001-integration-roadmap.md` is retired.

Re-run immediately before the migration regardless — the check is instant and
the data keeps moving.

### Implementation

In `backend/app/database.py`, after `engine` is created. This must be a
connection-level event listener, not a one-off statement: `foreign_keys` is
per-connection, and the pool opens many.

```python
from sqlalchemy import event

@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()
```

Notes:

- `journal_mode=WAL` is **persistent** — it's a property of the database file,
  set once and surviving reconnection. Re-issuing it is harmless.
- `busy_timeout=5000` makes a contending connection wait up to 5s for a lock
  instead of failing immediately. This is what makes two processes tolerable.
- `foreign_keys` and `busy_timeout` are per-connection and must be re-issued
  every time — hence the listener.
- The MCP server must set the same pragmas on its read-write connection.
  `reference/qs_mcp.py:54` already issues `PRAGMA foreign_keys = ON` in `_rw()`;
  it needs `busy_timeout` adding too.

### WAL and Docker

WAL creates `helf.db-wal` and `helf.db-shm` beside the database. Both live in
the mounted data directory (`/mnt/fast/apps/helf/data`) and must be on the same
filesystem as the database — they are, since it's one bind mount.

**WAL requires real shared-memory support and does not work reliably over
network filesystems** (NFS, SMB). The default `/mnt/fast` path suggests local
storage; confirm this before deploying. If the data directory is ever moved to a
network mount, WAL must be reconsidered — and with it, the two-process design in
ADR-0002.

Backup implication: copying `helf.db` alone is no longer sufficient while the
app is running, because recent commits may live in the `-wal` file. Use
`sqlite3 helf.db ".backup 'helf.db.bak'"` for a consistent hot copy, or stop the
container first.

### Rollback

Remove the listener. `journal_mode` persists in the file and must be reverted
explicitly if desired:

```bash
sqlite3 "$HELF_DATA_PATH/helf.db" "PRAGMA journal_mode=DELETE;"
```

---

## 3. Files touched

| File | Change |
|------|--------|
| `backend/pyproject.toml` | add `alembic>=1.14.0` |
| `backend/alembic.ini` | new — generated, then edited |
| `backend/migrations/alembic/env.py` | new — wire to `settings` + `Base.metadata`, `render_as_batch=True` |
| `backend/migrations/alembic/versions/*.py` | new — baseline revision |
| `backend/app/database.py` | pragma listener; `init_db()` runs `upgrade head` |
| `backend/tests/conftest.py` | keep `create_all()` for tests; verify pragmas apply |
| `Dockerfile` | ensure `migrations/` is copied into the image |

`Dockerfile` is easy to miss: if `migrations/` isn't in the image, `init_db()`
raises at container start rather than at build.

---

## 4. Verification

```bash
# FK enforcement is live
sqlite3 "$HELF_DATA_PATH/helf.db" "PRAGMA foreign_keys;"    # -> 1 (per-connection; check via the app)
sqlite3 "$HELF_DATA_PATH/helf.db" "PRAGMA journal_mode;"    # -> wal
ls "$HELF_DATA_PATH"/helf.db-wal                            # exists while running

# migrations are wired
cd backend && alembic current      # -> baseline revision
alembic check                      # -> no drift between models and DB
```

Add a test asserting the pragmas are actually set on a pooled connection — this
is exactly the kind of configuration that regresses silently:

```python
def test_pragmas_applied(db_session):
    assert db_session.execute(text("PRAGMA foreign_keys")).scalar() == 1
```

`alembic check` is worth wiring into CI: it fails when the ORM models drift from
the migration history, which is the failure mode this whole plan exists to
prevent.
