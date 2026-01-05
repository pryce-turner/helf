import pytest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from app.db.models import Category, Exercise
from app.utils.date_helpers import PACIFIC_TZ

module_path = Path(__file__).resolve().parents[1] / "migrations" / "tinydb_to_sqlite.py"
spec = spec_from_file_location("tinydb_to_sqlite", module_path)
tinydb_to_sqlite = module_from_spec(spec)
spec.loader.exec_module(tinydb_to_sqlite)

parse_datetime = tinydb_to_sqlite.parse_datetime
ensure_category = tinydb_to_sqlite.ensure_category
ensure_exercise = tinydb_to_sqlite.ensure_exercise

pytestmark = pytest.mark.usefixtures("db_engine")


def test_parse_datetime_assigns_timezone():
    dt = parse_datetime("2024-01-01T12:00:00")
    assert dt.tzinfo == PACIFIC_TZ


def test_ensure_category_reuses_existing(db_session):
    category = ensure_category(db_session, "Pull", None, {})
    again = ensure_category(db_session, "Pull", None, {})

    stored = db_session.query(Category).filter(Category.name == "Pull").all()
    assert len(stored) == 1
    assert category.id == again.id


def test_ensure_exercise_sets_defaults(db_session):
    category = ensure_category(db_session, "Push", None, {})
    exercise = ensure_exercise(
        db_session,
        "Bench",
        category,
        None,
        None,
        None,
        {},
    )
    stored = db_session.query(Exercise).filter(Exercise.name == "Bench").one()
    assert stored.use_count == 0
    assert stored.last_used is None
    assert exercise.id == stored.id
