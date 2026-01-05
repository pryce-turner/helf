"""Database setup and connection management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


def _build_db_url() -> str:
    db_path = settings.db_path
    return f"sqlite:///{db_path}"


class Base(DeclarativeBase):
    """Base class for ORM models."""


engine = create_engine(
    _build_db_url(),
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db():
    """Create database tables if they do not exist."""
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


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
