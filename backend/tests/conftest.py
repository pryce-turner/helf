import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.database as database
import app.repositories.body_comp_repo as body_comp_repo
import app.repositories.exercise_repo as exercise_repo
import app.repositories.upcoming_repo as upcoming_repo
import app.repositories.workout_repo as workout_repo
from app.api import body_comp, exercises, food, notes, progression, upcoming, workouts
from app.database import apply_sqlite_pragmas


@pytest.fixture()
def db_engine(tmp_path, monkeypatch):
    """A database built the way production is: by running the migrations.

    This used to call `Base.metadata.create_all()`, which was cheaper and was
    fine while the schema was only tables. It is no longer viable - the read
    path queries views, and `metric_def` carries a seeded vocabulary, and
    neither exists in metadata. `create_all()` would produce a database the
    application cannot actually run against.

    Migrating an empty SQLite file costs a few milliseconds, and it means the
    suite exercises the same startup path the container does.
    """
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    # Same pragmas as production. Tests that pass with foreign keys unenforced
    # and fail with them enforced are the whole reason to do this here.
    apply_sqlite_pragmas(engine)
    # PascalCase deliberately: this is a sessionmaker factory, and it is patched
    # in as `database.SessionLocal`, whose name it should match.
    SessionLocal = sessionmaker(  # noqa: N806
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", SessionLocal)
    monkeypatch.setattr(database.settings, "db_path", db_path)

    # Only the modules that did `from app.database import SessionLocal`, which
    # binds the production engine at import time. `food_repo` and `note_repo`
    # reference `database.SessionLocal` through the module and are covered by
    # the patch above; they deliberately do not appear here.
    for module in (exercise_repo, workout_repo, upcoming_repo, body_comp_repo):
        monkeypatch.setattr(module, "SessionLocal", SessionLocal)

    command.upgrade(Config(str(database.ALEMBIC_INI)), "head")

    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    SessionLocal = sessionmaker(  # noqa: N806 - sessionmaker factory, see above
        bind=db_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_engine):
    app = FastAPI()
    app.include_router(workouts.router, prefix="/api/workouts")
    app.include_router(exercises.router, prefix="/api/exercises")
    app.include_router(progression.router, prefix="/api/progression")
    app.include_router(upcoming.router, prefix="/api/upcoming")
    app.include_router(body_comp.router, prefix="/api/body-composition")
    app.include_router(food.router, prefix="/api/food")
    app.include_router(notes.router, prefix="/api/notes")
    return TestClient(app)
