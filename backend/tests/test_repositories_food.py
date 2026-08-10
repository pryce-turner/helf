import pytest
from sqlalchemy.exc import IntegrityError

from app.models.food import FoodCreate, FoodLogCreate, FoodUpdate
from app.repositories.food_repo import FoodLogRepository, FoodRepository

pytestmark = pytest.mark.usefixtures("db_engine")


def _egg(**overrides) -> FoodCreate:
    fields = {"name": "Egg", "kcal_per_serving": 78, "protein_g": 6.3, "carb_g": 0.6, "fat_g": 5.3}
    fields.update(overrides)
    return FoodCreate(**fields)


def test_food_log_date_is_generated_from_consumed_at():
    """The single most likely thing to break: `date` is a SQLite GENERATED
    column, and SQLAlchemy must be told not to write to it."""
    food = FoodRepository().create(_egg())
    entry = FoodLogRepository().create(
        FoodLogCreate(food_id=food["doc_id"], servings=2, consumed_at="2026-08-07T08:00:00")
    )
    assert entry["date"] == "2026-08-07"


def test_food_log_scales_macros_by_servings():
    food = FoodRepository().create(_egg())
    entry = FoodLogRepository().create(
        FoodLogCreate(food_id=food["doc_id"], servings=2, consumed_at="2026-08-07T08:00:00")
    )
    assert entry["kcal"] == 156
    assert entry["protein_g"] == 12.6


def test_brandless_foods_collide_on_name():
    """`brand` is '' and not NULL precisely so this is a constraint and not a
    suggestion - SQLite treats NULLs as distinct in a UNIQUE index."""
    repo = FoodRepository()
    first = repo.create(_egg())
    again = repo.create(_egg(kcal_per_serving=999))
    assert again["doc_id"] == first["doc_id"]
    # Resolved to the existing row, so the second call's macros are ignored
    # rather than overwriting - editing macros is an explicit PUT.
    assert again["kcal_per_serving"] == 78


def test_brand_distinguishes_same_named_foods():
    repo = FoodRepository()
    plain = repo.create(_egg())
    branded = repo.create(_egg(brand="Vital Farms"))
    assert plain["doc_id"] != branded["doc_id"]


def test_null_brand_is_stored_as_empty_string():
    food = FoodRepository().create(FoodCreate(name="Chicken", brand=None))
    assert food["brand"] == ""


def test_log_by_name_creates_the_food():
    entry = FoodLogRepository().create(
        FoodLogCreate(food=_egg(), servings=1, consumed_at="2026-08-07T08:00:00")
    )
    assert entry["name"] == "Egg"
    assert FoodRepository().search("Egg")[0]["doc_id"] == entry["food_id"]


def test_log_with_unknown_food_id_returns_none():
    """Rather than letting the FK violation surface as a 500. Pragmas enforce
    foreign keys in every environment, including this one."""
    assert (
        FoodLogRepository().create(FoodLogCreate(food_id=9999, servings=1)) is None
    )


def test_editing_a_food_rewrites_past_entries():
    """Macros live on `food`, not on the log, so a correction is retroactive.
    This is the intended behaviour and worth pinning down."""
    repo = FoodRepository()
    log_repo = FoodLogRepository()
    food = repo.create(_egg())
    log_repo.create(
        FoodLogCreate(food_id=food["doc_id"], servings=2, consumed_at="2026-08-07T08:00:00")
    )

    repo.update(food["doc_id"], FoodUpdate(kcal_per_serving=80))

    assert log_repo.get_by_date("2026-08-07")[0]["kcal"] == 160


def test_summary_coalesces_missing_macros_and_counts_them():
    """The one piece of real logic here. SUM over a NULL protein would blank
    the whole day's protein; the day reports a partial total plus the count of
    foods responsible for the gap."""
    repo = FoodRepository()
    log_repo = FoodLogRepository()
    known = repo.create(_egg())
    unknown = repo.create(FoodCreate(name="Leftovers", kcal_per_serving=400))

    for food_id in (known["doc_id"], unknown["doc_id"]):
        log_repo.create(
            FoodLogCreate(food_id=food_id, servings=1, consumed_at="2026-08-07T08:00:00")
        )

    day = log_repo.summary("2026-08-07", "2026-08-07")[0]
    assert day["kcal"] == 478
    assert day["protein_g"] == 6.3
    assert day["entries"] == 2
    assert day["foods_missing_macros"] == 1


def test_summary_omits_days_with_nothing_logged():
    """An unlogged day is not a fasted day. Reporting it as zero would put a
    false floor on the chart."""
    food = FoodRepository().create(_egg())
    log_repo = FoodLogRepository()
    log_repo.create(
        FoodLogCreate(food_id=food["doc_id"], servings=1, consumed_at="2026-08-07T08:00:00")
    )

    dates = [d["date"] for d in log_repo.summary("2026-08-01", "2026-08-31")]
    assert dates == ["2026-08-07"]


def test_delete_removes_the_entry_not_the_food():
    food = FoodRepository().create(_egg())
    log_repo = FoodLogRepository()
    entry = log_repo.create(
        FoodLogCreate(food_id=food["doc_id"], servings=1, consumed_at="2026-08-07T08:00:00")
    )

    assert log_repo.delete(entry["doc_id"]) is True
    assert log_repo.delete(entry["doc_id"]) is False
    assert log_repo.get_by_date("2026-08-07") == []
    assert FoodRepository().get_by_id(food["doc_id"]) is not None


def test_meal_check_constraint_rejects_unknown_meals():
    """Enforced by the database, not only by the Pydantic Literal - the agent
    writes this table with raw SQL (ADR-0002)."""
    from app import database
    from app.db.models import Food, FoodLog

    with database.SessionLocal() as session:
        session.add(Food(name="Egg", brand="", created_at="2026-08-07"))
        session.flush()
        session.add(
            FoodLog(
                consumed_at="2026-08-07T08:00:00",
                food_id=1,
                servings=1,
                meal="elevenses",
                created_at="2026-08-07",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
