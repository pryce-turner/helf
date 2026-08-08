"""Tests for engine configuration and migration bootstrapping.

Pragmas and migration wiring are exactly the kind of configuration that
regresses silently: nothing fails loudly when foreign keys stop being enforced,
it just starts accepting bad rows.
"""

import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import app.database as database
from app.database import Base, apply_sqlite_pragmas


class TestPragmas:
    def test_foreign_keys_enforced(self, db_session):
        assert db_session.execute(text("PRAGMA foreign_keys")).scalar() == 1

    def test_journal_mode_is_wal(self, db_session):
        assert db_session.execute(text("PRAGMA journal_mode")).scalar() == "wal"

    def test_busy_timeout_set(self, db_session):
        assert db_session.execute(text("PRAGMA busy_timeout")).scalar() == 5000

    def test_pragmas_apply_to_every_pooled_connection(self, db_engine):
        # Per-connection pragmas are re-issued by the listener, not set once.
        for _ in range(3):
            with db_engine.connect() as conn:
                assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1

    def test_orphan_foreign_key_is_rejected(self, db_session):
        """The point of foreign_keys=ON: a dangling reference must not insert."""
        from datetime import datetime

        from app.db.models import Workout

        db_session.add(
            Workout(
                date="2026-01-01",
                exercise_id=99999,  # does not exist
                category_id=99999,  # does not exist
                weight_unit="lbs",
                order=1,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        )
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_engine_without_pragmas_does_not_enforce(self, tmp_path):
        """Guards the test above: absent the listener, SQLite lets the orphan in.

        Without this, `test_orphan_foreign_key_is_rejected` could pass for the
        wrong reason and nobody would notice the listener had been removed.
        """
        db_path = tmp_path / "bare.db"
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(bind=engine)
        try:
            with engine.connect() as conn:
                assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 0
        finally:
            engine.dispose()


class TestInitDb:
    """`init_db()` has to serve two very different databases."""

    @staticmethod
    def _point_at(monkeypatch, db_path):
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        apply_sqlite_pragmas(engine)
        monkeypatch.setattr(database, "engine", engine)
        monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))
        # env.py resolves the URL from this same settings object.
        monkeypatch.setattr(database.settings, "db_path", db_path)
        return engine

    def test_fresh_database_is_built_from_migrations(self, tmp_path, monkeypatch):
        engine = self._point_at(monkeypatch, tmp_path / "fresh.db")
        try:
            database.init_db()
            tables = set(inspect(engine).get_table_names())
            assert {
                "workouts",
                "upcoming_workouts",
                "exercises",
                "categories",
                "body_composition",
            } <= tables
            with engine.connect() as conn:
                assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        finally:
            engine.dispose()

    def test_pre_alembic_database_is_stamped_not_replayed(self, tmp_path, monkeypatch):
        """A database created before Alembic must be adopted, not rebuilt.

        Replaying the baseline against it fails on the first CREATE TABLE.
        """
        db_path = tmp_path / "legacy.db"
        legacy = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(bind=legacy)
        with legacy.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO categories (id, name, created_at) "
                    "VALUES (1, 'Legs', '2026-01-01 00:00:00')"
                )
            )
        legacy.dispose()

        engine = self._point_at(monkeypatch, db_path)
        try:
            database.init_db()
            with engine.connect() as conn:
                assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
                # The pre-existing row survived, i.e. nothing was recreated.
                assert conn.execute(text("SELECT count(*) FROM categories")).scalar() == 1
        finally:
            engine.dispose()

    def test_empty_alembic_version_table_still_stamps(self, tmp_path, monkeypatch):
        """Regression: connecting creates `alembic_version` empty.

        Testing for the table's existence rather than for a recorded revision
        skips the stamp and replays the baseline against a populated database.
        """
        db_path = tmp_path / "halfway.db"
        legacy = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(bind=legacy)
        legacy.dispose()

        raw = sqlite3.connect(db_path)
        raw.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        raw.commit()
        raw.close()

        engine = self._point_at(monkeypatch, db_path)
        try:
            database.init_db()
            with engine.connect() as conn:
                assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        finally:
            engine.dispose()

    def test_init_db_is_idempotent(self, tmp_path, monkeypatch):
        engine = self._point_at(monkeypatch, tmp_path / "twice.db")
        try:
            database.init_db()
            with engine.connect() as conn:
                first = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            database.init_db()
            with engine.connect() as conn:
                assert (
                    conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == first
                )
        finally:
            engine.dispose()


def test_models_match_migrations(tmp_path, monkeypatch):
    """`alembic check` as a test: fails when the ORM drifts from the history.

    This is the failure mode the whole migration setup exists to prevent - a
    model changed, no revision written, and the difference only surfaces as a
    query error in production.
    """
    from alembic import command
    from alembic.config import Config
    from alembic.util.exc import AutogenerateDiffsDetected

    db_path = tmp_path / "drift.db"
    monkeypatch.setattr(database.settings, "db_path", db_path)

    cfg = Config(str(database.ALEMBIC_INI))
    command.upgrade(cfg, "head")
    try:
        command.check(cfg)
    except AutogenerateDiffsDetected as exc:
        pytest.fail(f"Models have drifted from migrations - write a revision:\n{exc}")
