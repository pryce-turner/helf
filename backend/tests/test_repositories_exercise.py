import pytest

from app.models.exercise import CategoryCreate, ExerciseCreate, ExerciseUpdate
from app.repositories.exercise_repo import CategoryRepository, ExerciseRepository

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


def test_exercise_rating_defaults_to_unrated():
    """Unrated is not zero-rated, which is why there is no default."""
    repo = ExerciseRepository()
    created = repo.create(ExerciseCreate(name="Hip Airplane", category="Legs"))
    assert created["rating"] is None


def test_an_exercise_carries_no_mobility_judgement():
    """Mobility is a property of the set now (d7e4f2a91b83).

    The movement cannot answer it: a good morning is a loaded hinge in one
    session and a loaded stretch in the next. `rating` stays here because it
    *is* an opinion about the movement.
    """
    repo = ExerciseRepository()
    created = repo.create(ExerciseCreate(name="Cossack Squat", category="Legs"))

    assert "is_mobility" not in created

    updated = repo.update(created["doc_id"], ExerciseUpdate(rating=5))
    assert updated["rating"] == 5


def test_exercise_update_can_clear_a_rating():
    """`rating: null` means unrate, which an `is not None` guard would drop.

    The distinction only exists in `model_fields_set` — by value alone an
    explicit null and an omitted field are identical.
    """
    repo = ExerciseRepository()
    created = repo.create(
        ExerciseCreate(name="Jefferson Curl", category="Back", rating=3)
    )
    assert created["rating"] == 3

    cleared = repo.update(created["doc_id"], ExerciseUpdate(rating=None))
    assert cleared["rating"] is None


def test_exercise_update_without_rating_leaves_it_alone():
    """The other half of the same distinction: omitted must not clear."""
    repo = ExerciseRepository()
    created = repo.create(
        ExerciseCreate(name="Deep Squat Hold", category="Legs", rating=4)
    )

    renamed = repo.update(created["doc_id"], ExerciseUpdate(name="Squat Hold"))
    assert renamed["name"] == "Squat Hold"
    assert renamed["rating"] == 4
