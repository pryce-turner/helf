import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.database as database
from app.database import Base
from app.api import workouts, exercises, progression, upcoming, body_comp

import app.repositories.exercise_repo as exercise_repo
import app.repositories.workout_repo as workout_repo
import app.repositories.upcoming_repo as upcoming_repo
import app.repositories.body_comp_repo as body_comp_repo


@pytest.fixture()
def db_engine(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    SessionLocal = sessionmaker(
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
    try:
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    SessionLocal = sessionmaker(
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
