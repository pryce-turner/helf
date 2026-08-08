import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.database as database
import app.repositories.body_comp_repo as body_comp_repo
import app.repositories.exercise_repo as exercise_repo
import app.repositories.upcoming_repo as upcoming_repo
import app.repositories.workout_repo as workout_repo
from app.api import body_comp, exercises, progression, upcoming, workouts
from app.database import Base, apply_sqlite_pragmas
from app.db.models import MetricDef
from app.repositories.body_comp_repo import METRIC_COLUMNS


@pytest.fixture()
def db_engine(tmp_path, monkeypatch):
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

    for module in (exercise_repo, workout_repo, upcoming_repo, body_comp_repo):
        monkeypatch.setattr(module, "SessionLocal", SessionLocal)

    Base.metadata.create_all(bind=engine)

    # In production `metric_def` is seeded by migration, but these fixtures
    # build schema with create_all(), which creates the table empty. Without
    # this, every mirrored metric write fails its foreign key - and because the
    # mirror is deliberately non-fatal, the tests would pass while the dual
    # write silently did nothing.
    with SessionLocal() as session:
        for _column, name, unit in METRIC_COLUMNS:
            session.add(MetricDef(name=name, canonical_unit=unit))
        session.commit()

    try:
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)
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
    return TestClient(app)
