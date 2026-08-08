"""Database setup and connection management."""

from pathlib import Path

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def _build_db_url() -> str:
    db_path = settings.db_path
    return f"sqlite:///{db_path}"


class Base(DeclarativeBase):
    """Base class for ORM models."""


def apply_sqlite_pragmas(target: Engine) -> None:
    """Set the pragmas SQLite does not default to sensibly.

    Registered as a connect-time listener rather than issued once: ``foreign_keys``
    and ``busy_timeout`` are per-connection settings, and the pool opens many
    connections over the process's life.

    Exposed as a function so the test suite can hold its engines to the same
    rules as production - foreign keys being unenforced in tests but enforced in
    production is exactly how a constraint violation reaches a user.
    """

    @event.listens_for(target, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        # Off by default in SQLite, per connection. Every ForeignKey in
        # db/models.py is inert without this.
        cursor.execute("PRAGMA foreign_keys=ON")
        # Persistent property of the file, but harmless to re-issue. Rollback
        # journal takes a database-wide write lock, which a second process
        # (the MCP server) would contend with constantly.
        cursor.execute("PRAGMA journal_mode=WAL")
        # Wait for a lock rather than failing instantly with "database is
        # locked". This is what makes two processes on one file tolerable.
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


engine = create_engine(
    _build_db_url(),
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)

apply_sqlite_pragmas(engine)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db():
    """Bring the database up to the latest migration.

    Replaces ``Base.metadata.create_all()``, which can create missing tables but
    cannot alter existing ones - it silently does nothing for every column add,
    type change, or constraint change.
    """
    from alembic import command
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    from app.db import models  # noqa: F401 - registers tables on Base.metadata

    cfg = Config(str(ALEMBIC_INI))

    app_tables = set(inspect(engine).get_table_names()) - {"alembic_version"}
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()

    if app_tables and current is None:
        # A database that predates Alembic. Its schema already matches the
        # baseline, so record the baseline as applied instead of replaying it -
        # running those CREATE TABLEs here would fail on the first one.
        #
        # Test the recorded revision, not the presence of `alembic_version`:
        # alembic creates that table empty as a side effect of merely
        # connecting, so its existence proves nothing about what has run.
        script = ScriptDirectory.from_config(cfg)
        command.stamp(cfg, script.get_base())

    command.upgrade(cfg, "head")


def get_db():
    """Yield a database session for request-scoped use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def close_db():
    """Dispose of the engine connection pool."""
    engine.dispose()
