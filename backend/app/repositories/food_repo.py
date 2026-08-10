"""Food catalog and food log repository.

Every session comes from `database.SessionLocal` reached *through the module*,
not `from app.database import SessionLocal`. The import form binds the
production engine at import time and is only safe if `conftest`'s patch list
happens to name this module; a test that gets it wrong writes to
`data/helf.db`, which has happened here before.
"""

from sqlalchemy import delete, select, text

from app import database
from app.db.models import Food, FoodLog
from app.models.food import FoodCreate, FoodLogCreate, FoodUpdate
from app.utils.date_helpers import format_timestamp, get_current_datetime

# Daily totals come from `v_daily_summary` rather than being recomputed here,
# so the food page and the agent cannot disagree about what a day added up to.
# The view already coalesces NULL macros to zero and counts the foods
# responsible for the gap.
#
# The EXISTS excludes days with nothing logged: the view's spine is every day
# *anything* happened, and a day with three workouts and no food is not a
# zero-calorie day, it is an unlogged one.
DAILY_TOTALS_SQL = text(
    """
    SELECT s.date,
           s.kcal,
           s.protein_g,
           s.carb_g,
           s.fat_g,
           s.foods_missing_macros,
           (SELECT COUNT(*) FROM food_log fl WHERE fl.date = s.date) AS entries
    FROM v_daily_summary s
    WHERE s.date BETWEEN :start AND :end
      AND EXISTS (SELECT 1 FROM food_log fl WHERE fl.date = s.date)
    ORDER BY s.date
    """
)


def _entry(log: FoodLog, food: Food) -> dict:
    """Resolve a log row against its food, multiplying macros by servings.

    Derived at read time rather than stored, which is what makes a correction
    to a food's macros retroactive across every entry that used it.
    """

    def scaled(value: float | None) -> float | None:
        return None if value is None else round(value * log.servings, 2)

    return {
        "doc_id": log.id,
        "consumed_at": log.consumed_at,
        "date": log.date,
        "servings": log.servings,
        "meal": log.meal,
        "food_id": food.id,
        "name": food.name,
        "brand": food.brand,
        "serving_desc": food.serving_desc,
        "kcal": scaled(food.kcal_per_serving),
        "protein_g": scaled(food.protein_g),
        "carb_g": scaled(food.carb_g),
        "fat_g": scaled(food.fat_g),
    }


class FoodRepository:
    """The food catalog: names, brands, and macros per serving."""

    @staticmethod
    def _serialize(food: Food) -> dict:
        return {
            "doc_id": food.id,
            "name": food.name,
            "brand": food.brand,
            "serving_desc": food.serving_desc,
            "kcal_per_serving": food.kcal_per_serving,
            "protein_g": food.protein_g,
            "carb_g": food.carb_g,
            "fat_g": food.fat_g,
            "created_at": food.created_at,
        }

    def search(self, q: str | None = None, limit: int = 50) -> list[dict]:
        """Search the catalog by name or brand."""
        with database.SessionLocal() as session:
            stmt = select(Food).order_by(Food.name)
            if q:
                pattern = f"%{q}%"
                stmt = stmt.where(Food.name.ilike(pattern) | Food.brand.ilike(pattern))
            foods = session.execute(stmt.limit(limit)).scalars().all()
            return [self._serialize(f) for f in foods]

    def get_by_id(self, food_id: int) -> dict | None:
        with database.SessionLocal() as session:
            food = session.get(Food, food_id)
            return self._serialize(food) if food else None

    def resolve(self, session, food: FoodCreate) -> Food:
        """Find a food by `(name, brand)`, creating it when new.

        Both halves of the key are plain equality because `brand` is `''` and
        never NULL - see `Food` in `db/models.py` for why.
        """
        existing = session.execute(
            select(Food).where(Food.name == food.name, Food.brand == food.brand)
        ).scalar_one_or_none()
        if existing:
            return existing

        created = Food(
            name=food.name,
            brand=food.brand,
            serving_desc=food.serving_desc,
            kcal_per_serving=food.kcal_per_serving,
            protein_g=food.protein_g,
            carb_g=food.carb_g,
            fat_g=food.fat_g,
            created_at=format_timestamp(get_current_datetime()),
        )
        session.add(created)
        session.flush()
        return created

    def create(self, food: FoodCreate) -> dict:
        with database.SessionLocal() as session:
            resolved = self.resolve(session, food)
            session.commit()
            session.refresh(resolved)
            return self._serialize(resolved)

    def update(self, food_id: int, changes: FoodUpdate) -> dict | None:
        """Edit a food. Retroactively changes every past entry's totals."""
        with database.SessionLocal() as session:
            food = session.get(Food, food_id)
            if food is None:
                return None
            for field, value in changes.model_dump(exclude_unset=True).items():
                # A null brand means "brandless", which is stored as ''.
                if field == "brand" and value is None:
                    value = ""
                setattr(food, field, value)
            session.commit()
            session.refresh(food)
            return self._serialize(food)


class FoodLogRepository:
    """Consumption events."""

    def get_by_date(self, date: str) -> list[dict]:
        with database.SessionLocal() as session:
            rows = session.execute(
                select(FoodLog, Food)
                .join(Food, Food.id == FoodLog.food_id)
                .where(FoodLog.date == date)
                .order_by(FoodLog.consumed_at)
            ).all()
            return [_entry(log, food) for log, food in rows]

    def create(self, entry: FoodLogCreate) -> dict | None:
        """Log a consumption event.

        Returns None when `food_id` names a food that does not exist, which the
        API turns into a 404. Without the check SQLite raises an FK violation
        (pragmas are on in every environment) and the caller gets a 500.
        """
        consumed_at = entry.consumed_at or format_timestamp(get_current_datetime())

        with database.SessionLocal() as session:
            if entry.food_id is not None:
                food = session.get(Food, entry.food_id)
                if food is None:
                    return None
            else:
                food = FoodRepository().resolve(session, entry.food)

            log = FoodLog(
                consumed_at=consumed_at,
                food_id=food.id,
                servings=entry.servings,
                meal=entry.meal,
                created_at=format_timestamp(get_current_datetime()),
            )
            session.add(log)
            session.commit()
            session.refresh(log)
            return _entry(log, food)

    def delete(self, log_id: int) -> bool:
        with database.SessionLocal() as session:
            result = session.execute(delete(FoodLog).where(FoodLog.id == log_id))
            session.commit()
            return result.rowcount > 0

    def summary(self, start: str, end: str) -> list[dict]:
        """Daily kcal and macro totals over a date range, inclusive.

        See `DAILY_TOTALS_SQL` for why this reads the view and why days with
        nothing logged are absent rather than zero.
        """
        with database.SessionLocal() as session:
            rows = session.execute(
                DAILY_TOTALS_SQL, {"start": start, "end": end}
            ).all()
            return [
                {
                    "date": row.date,
                    "kcal": row.kcal,
                    "protein_g": row.protein_g,
                    "carb_g": row.carb_g,
                    "fat_g": row.fat_g,
                    "entries": row.entries,
                    "foods_missing_macros": row.foods_missing_macros,
                }
                for row in rows
            ]
