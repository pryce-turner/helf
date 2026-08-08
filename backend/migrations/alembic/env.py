"""Alembic environment.

Wired to the application's own settings and metadata rather than to a URL in
``alembic.ini``: the database location is already configurable via ``DATA_DIR`` /
``HELF_DATA_PATH`` (``app/config.py``) and must not be duplicated here.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, event, pool, text

from app.config import settings
from app.database import Base
from app.db import models  # noqa: F401 - registers tables on Base.metadata

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False: init_db() runs this in-process at app
    # startup, and the default would silence uvicorn's already-created loggers.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _db_url() -> str:
    return f"sqlite:///{settings.db_path}"


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting."""
    context.configure(
        url=_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    connectable = create_engine(_db_url(), poolclass=pool.NullPool)

    @event.listens_for(connectable, "connect")
    def _migration_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        # Foreign keys MUST be off for the duration of a migration. Alembic's
        # batch mode rebuilds a table by copying it to a temp table and renaming;
        # with foreign_keys=ON, SQLite helpfully rewrites referencing tables to
        # point at the temporary name, silently corrupting the schema. The
        # integrity check after run_migrations() is what replaces the guarantee.
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()

        violations = connection.execute(text("PRAGMA foreign_key_check")).fetchall()
        if violations:
            raise RuntimeError(
                f"Migration left {len(violations)} foreign key violation(s): "
                f"{violations[:5]}"
            )

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
