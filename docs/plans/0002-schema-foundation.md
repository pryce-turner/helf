# Plan 0002: Schema foundation

**Status:** **Done** — implemented 2026-08-08, baseline revision `ac2fc3529985`
**Prerequisites:** none
**Blocks:** every other plan
**Related:** ADR-0002, ADR-0004

> ## Implementation notes
>
> Executed as written except for four points where the plan was wrong or silent.
> Recorded here because each was discovered by running the thing, not by reading.
>
> **1. The baseline holds the full schema, not nothing.** §1.5 said to autogenerate
> against the live database and expect an empty revision. That check passed —
> models and production matched exactly, no drift — but an *empty* baseline is
> unusable: once `init_db()` is `upgrade head`, a fresh deployment would create
> no tables at all. The baseline was regenerated against an empty database so it
> contains every `CREATE TABLE`. Existing databases are `stamp`ed instead of
> having it replayed.
>
> **2. `init_db()` stamps pre-Alembic databases automatically.** The plan's
> `init_db()` was `upgrade head` alone, which fails against production with
> `table body_composition already exists`. It now detects an unversioned database
> and stamps the baseline first.
>
> The first attempt tested for the *presence* of `alembic_version` — wrong, and it
> failed exactly that way in testing: Alembic creates that table empty as a side
> effect of merely connecting, so `alembic revision --autogenerate` had already
> left one behind. The guard now tests for a **recorded revision** via
> `MigrationContext.get_current_revision()`. Regression test:
> `tests/test_database.py::test_empty_alembic_version_table_still_stamps`.
>
> **3. Migrations run with `foreign_keys=OFF`, then a `foreign_key_check`.** Not in
> the plan, and it matters. Batch mode rebuilds a table by copying to a temp table
> and renaming; with `foreign_keys=ON`, SQLite *helpfully rewrites referencing
> tables to point at the temporary name*, silently corrupting the schema.
> `exercises` and `categories` are both referenced, so this would fire the first
> time either is rebuilt. `env.py` disables FKs for the migration connection and
> raises if the post-migration integrity check finds violations.
>
> **4. `data/` was never actually gitignored.** `.gitignore` had `**/helf.db`,
> which does not match `helf.db-wal` or `helf.db-shm` — the sidecars WAL creates.
> Enabling WAL would have started committing them. Fixed alongside.
>
> Verified: `alembic current` → `ac2fc3529985 (head)`; `alembic check` → no drift;
> `foreign_keys=1`, `journal_mode=wal`, `busy_timeout=5000` as the app sees them;
> 9,292 workouts / 150 body_composition / 173 exercises intact through adoption;
> image layout exercised from `/` to confirm no working-directory dependency.
>
> Test suite: 130 passed, 2 failed — both pre-existing at `HEAD` (confirmed in a
> clean worktree) and both fixed by Plan 0009.

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

### This is no longer hypothetical

Merge `1a27a0b` added `Exercise.notes` (`db/models.py:37`) and, because
`create_all()` cannot add a column to an existing table, shipped
`backend/migrations/add_exercise_notes.py` alongside it — a hand-rolled script
that opens `sqlite3` directly, inspects `PRAGMA table_info`, and issues a bare
`ALTER TABLE exercises ADD COLUMN notes TEXT`.

It works, and it is exactly the pattern this plan exists to replace:

- **No version tracking.** Nothing records that it ran. Its only idempotency is
  an inline column-existence check, hand-written per migration.
- **No downgrade.**
- **Run manually**, with the DB path as `argv[1]`. Forgetting it on any
  environment leaves a schema the ORM believes exists — and the failure surfaces
  as a query error at runtime, not at startup.
- **It won't compose.** A second such script has no defined ordering relative to
  the first.

One ad-hoc script is tolerable. The roadmap ahead adds `metric`, `metric_def`,
`document`, `note`, `food`, `food_log`, `audit_log`, a `reps` type change, and a
unit conversion. Hand-rolling that sequence, in order, idempotently, across two
environments is precisely what Alembic does correctly.

**Migrate `add_exercise_notes.py` into the Alembic baseline** rather than leaving
two mechanisms live. The prod copy at `data/helf.db` already has the column, so
the baseline must reflect a schema where `notes` exists — verified:
`PRAGMA table_info(exercises)` lists it.

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
the mounted data directory and must be on the same filesystem as the database —
they are, since it's one bind mount.

**Resolved: the database is `data/helf.db` in the repository directory, on local
disk**, and that directory is what gets bind-mounted into the container. The
earlier open question — whether the data path was network storage, which would
have invalidated WAL and with it ADR-0002's two-process design — does not apply.

Confirmed empirically: running the image against a fresh volume produced
`helf.db`, `helf.db-wal` and `helf.db-shm`, so WAL is genuinely active in the
container rather than silently falling back.

This constraint still binds any *future* relocation. **WAL requires real
shared-memory support and does not work reliably over network filesystems**
(NFS, SMB). Moving the data directory onto one means reverting WAL and
revisiting ADR-0002.

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
