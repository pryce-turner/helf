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


# --- Field configuration (plan 0018) ---------------------------------------


def test_a_new_exercise_keeps_the_current_editor():
    """Reps and Weight are what the day view offers today, so they start
    enabled; Distance and Time start off and out of the way. Every default
    starts NULL - enabled with no default means "offer the input, leave it
    blank"."""
    repo = ExerciseRepository()
    created = repo.create(ExerciseCreate(name="Squat", category="Legs"))

    assert created["reps_enabled"] is True
    assert created["weight_enabled"] is True
    assert created["distance_enabled"] is False
    assert created["time_enabled"] is False
    assert created["movement_break_enabled"] is False
    for field in (
        "default_reps",
        "default_weight_lb",
        "default_distance",
        "default_distance_unit",
        "default_work_seconds",
        "default_rest_seconds",
        "default_rest_after_seconds",
    ):
        assert created[field] is None


def test_field_groups_are_independent():
    """Each group's toggle is its own fact: Time on does not turn Distance on."""
    repo = ExerciseRepository()
    created = repo.create(ExerciseCreate(name="Farmer Carry", category="Legs"))

    updated = repo.update(
        created["doc_id"],
        ExerciseUpdate(
            time_enabled=True,
            default_work_seconds=40,
            default_rest_seconds=20,
            default_rest_after_seconds=15,
        ),
    )

    assert updated["time_enabled"] is True
    assert updated["default_work_seconds"] == 40
    assert updated["default_rest_seconds"] == 20
    assert updated["default_rest_after_seconds"] == 15
    assert updated["distance_enabled"] is False
    assert updated["reps_enabled"] is True


def test_a_default_is_cleared_by_an_explicit_null_and_kept_by_an_omission():
    """Same distinction as `rating`: blanking a default is a real edit, so an
    omitted key and a null are told apart by `model_fields_set`."""
    repo = ExerciseRepository()
    created = repo.create(
        ExerciseCreate(
            name="Sled Push",
            category="Legs",
            time_enabled=True,
            default_work_seconds=30,
        )
    )
    assert created["default_work_seconds"] == 30

    # An unrelated edit leaves the default where it was.
    renamed = repo.update(created["doc_id"], ExerciseUpdate(form="drive low"))
    assert renamed["default_work_seconds"] == 30

    cleared = repo.update(created["doc_id"], ExerciseUpdate(default_work_seconds=None))
    assert cleared["default_work_seconds"] is None
    # Disabling the group does not erase its configuration either (plan 0018:
    # re-enabling must not force the user to set it up again).
    disabled = repo.update(created["doc_id"], ExerciseUpdate(time_enabled=False))
    assert disabled["time_enabled"] is False


def test_the_movement_break_pool_reads_the_flag_not_a_bout():
    repo = ExerciseRepository()
    repo.create(ExerciseCreate(name="Barbell Squat", category="Legs"))
    repo.create(
        ExerciseCreate(
            name="Deep Squat Hold",
            category="Legs",
            movement_break_enabled=True,
            time_enabled=True,
            default_work_seconds=40,
        )
    )

    pool = repo.get_movement_breaks()
    assert [exercise["name"] for exercise in pool] == ["Deep Squat Hold"]
    assert pool[0]["movement_break_enabled"] is True
    assert pool[0]["default_work_seconds"] == 40
