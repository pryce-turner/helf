import pytest

from app.models.exercise import ExerciseCreate, CategoryCreate
from app.repositories.exercise_repo import ExerciseRepository, CategoryRepository

pytestmark = pytest.mark.usefixtures("db_engine")


def test_exercise_create_returns_existing():
    repo = ExerciseRepository()
    created = repo.create(ExerciseCreate(name="Squat", category="Legs"))
    duplicate = repo.create(ExerciseCreate(name="Squat", category="Legs"))
    assert duplicate["doc_id"] == created["doc_id"]


def test_exercise_get_by_category_orders_by_last_used():
    repo = ExerciseRepository()
    repo.create(ExerciseCreate(name="Squat", category="Legs"))
    repo.create(ExerciseCreate(name="Lunge", category="Legs"))

    repo.update_usage("Squat", "2024-01-03")
    repo.update_usage("Lunge", "2024-01-05")

    results = repo.get_by_category("Legs")
    assert [r["name"] for r in results] == ["Lunge", "Squat"]


def test_exercise_get_recent_filters_null_last_used():
    repo = ExerciseRepository()
    repo.create(ExerciseCreate(name="Bench", category="Push"))
    repo.create(ExerciseCreate(name="Press", category="Push"))
    repo.update_usage("Bench", "2024-01-04")

    recent = repo.get_recent(limit=5)
    assert [r["name"] for r in recent] == ["Bench"]


def test_category_create_returns_existing():
    repo = CategoryRepository()
    created = repo.create(CategoryCreate(name="Core"))
    duplicate = repo.create(CategoryCreate(name="Core"))
    assert duplicate["doc_id"] == created["doc_id"]


def test_category_get_all_sorts_by_name():
    repo = CategoryRepository()
    repo.create(CategoryCreate(name="Zed"))
    repo.create(CategoryCreate(name="Alpha"))

    results = repo.get_all()
    assert [r["name"] for r in results] == ["Alpha", "Zed"]
