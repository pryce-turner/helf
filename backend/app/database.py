"""Database setup and connection management."""

from tinydb import TinyDB
from tinydb.middlewares import CachingMiddleware
from tinydb.storages import JSONStorage
from app.config import settings

# Global database instance
_db: TinyDB | None = None


def get_db() -> TinyDB:
    """Get or create the database instance."""
    global _db
    if _db is None:
        _db = TinyDB(
            settings.db_path,
            storage=CachingMiddleware(JSONStorage),
            indent=2,
            ensure_ascii=False
        )
    return _db


def close_db():
    """Close the database connection."""
    global _db
    if _db is not None:
        _db.close()
        _db = None


def get_table(name: str):
    """Get a table from the database."""
    db = get_db()
    return db.table(name)


# Table names
WORKOUTS_TABLE = "workouts"
UPCOMING_TABLE = "upcoming_workouts"
BODY_COMP_TABLE = "body_composition"
EXERCISES_TABLE = "exercises"
CATEGORIES_TABLE = "categories"
