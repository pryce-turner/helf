"""Food catalog and food log repository.

Every session comes from `database.SessionLocal` reached *through the module*,
not `from app.database import SessionLocal`. The import form binds the
production engine at import time and is only safe if `conftest`'s patch list
happens to name this module; a test that gets it wrong writes to
`data/helf.db`, which has happened here before.
"""

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError

from app import database
from app.db.models import Food, FoodLog, Stack, StackItem
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
_DAILY_TOTALS_COLUMNS = """
    SELECT s.date,
           s.kcal,
           s.protein_g,
           s.carb_g,
           s.fat_g,
           s.foods_missing_macros,
           s.supplements_taken,
           s.kcal_target,
           (SELECT COUNT(*) FROM food_log fl WHERE fl.date = s.date) AS entries
    FROM v_daily_summary s
"""

DAILY_TOTALS_SQL = text(
    _DAILY_TOTALS_COLUMNS
    + """
    WHERE s.date BETWEEN :start AND :end
      AND EXISTS (SELECT 1 FROM food_log fl WHERE fl.date = s.date)
    ORDER BY s.date
    """
)

# One named day, whether or not the view has a row for it. The view's spine is
# every day something happened, and "today, so far" is routinely not one of
# them - a page opened before the first meal would otherwise show no target at
# exactly the moment the target is worth reading.
#
# `kcal_target` falls back to the most recent day that has one, which is
# correct because the view already carries it forward from the last scan. The
# multiplier stays in the view and is not duplicated here.
ONE_DAY_TOTALS_SQL = text(
    """
    SELECT :date AS date,
           s.kcal,
           s.protein_g,
           s.carb_g,
           s.fat_g,
           COALESCE(s.foods_missing_macros, 0) AS foods_missing_macros,
           COALESCE(s.supplements_taken, 0) AS supplements_taken,
           COALESCE(
               s.kcal_target,
               (SELECT p.kcal_target FROM v_daily_summary p
                 WHERE p.date <= :date AND p.kcal_target IS NOT NULL
                 ORDER BY p.date DESC LIMIT 1)
           ) AS kcal_target,
           (SELECT COUNT(*) FROM food_log fl WHERE fl.date = :date) AS entries
    FROM (SELECT 1) one
    LEFT JOIN v_daily_summary s ON s.date = :date
    """
)


class DuplicateFoodError(Exception):
    """A rename collided with UNIQUE (name, brand)."""


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
        "kind": food.kind,
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
            "kind": food.kind,
            "serving_desc": food.serving_desc,
            "kcal_per_serving": food.kcal_per_serving,
            "protein_g": food.protein_g,
            "carb_g": food.carb_g,
            "fat_g": food.fat_g,
            "created_at": food.created_at,
        }

    def search(
        self, q: str | None = None, limit: int = 50, kind: str | None = None
    ) -> list[dict]:
        """Search the catalog by name or brand, optionally one kind.

        The food page filters to `kind='food'` so a typeahead for "mag" offers
        mango rather than magnesium; the supplements page does the reverse.
        """
        with database.SessionLocal() as session:
            stmt = select(Food).order_by(Food.name)
            if kind:
                stmt = stmt.where(Food.kind == kind)
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
            kind=food.kind,
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

    def usage(self, food_id: int) -> dict | None:
        """How much history an edit to this food would rewrite."""
        with database.SessionLocal() as session:
            if session.get(Food, food_id) is None:
                return None
            entries, first, last = session.execute(
                select(
                    func.count(FoodLog.id),
                    func.min(FoodLog.date),
                    func.max(FoodLog.date),
                ).where(FoodLog.food_id == food_id)
            ).one()
            stacks = (
                session.execute(
                    select(Stack.name)
                    .join(StackItem, StackItem.stack_id == Stack.id)
                    .where(StackItem.food_id == food_id)
                    .order_by(Stack.order, Stack.name)
                )
                .scalars()
                .all()
            )
        return {
            "food_id": food_id,
            "entries": entries,
            "first_logged": first,
            "last_logged": last,
            "stacks": list(stacks),
        }

    def update(self, food_id: int, changes: FoodUpdate) -> dict | None:
        """Edit a food. Retroactively changes every past entry's totals.

        Raises `DuplicateFoodError` when the new `(name, brand)` already belongs to
        something else. Without the catch that surfaces as an uncaught
        IntegrityError and a 500, which tells the user their edit crashed the
        app rather than that the name is taken.
        """
        with database.SessionLocal() as session:
            food = session.get(Food, food_id)
            if food is None:
                return None
            for field, value in changes.model_dump(exclude_unset=True).items():
                # A null brand means "brandless", which is stored as ''.
                if field == "brand" and value is None:
                    value = ""
                setattr(food, field, value)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise DuplicateFoodError(
                    f"'{food.name}' already exists"
                    + (f" under brand '{food.brand}'" if food.brand else "")
                ) from exc
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

    @staticmethod
    def _totals(row) -> dict:
        return {
            "date": row.date,
            "kcal": row.kcal,
            "protein_g": row.protein_g,
            "carb_g": row.carb_g,
            "fat_g": row.fat_g,
            "entries": row.entries,
            "foods_missing_macros": row.foods_missing_macros,
            "supplements_taken": row.supplements_taken,
            "kcal_target": row.kcal_target,
        }

    def summary(self, start: str, end: str) -> list[dict]:
        """Daily kcal and macro totals over a date range, inclusive.

        See `DAILY_TOTALS_SQL` for why this reads the view and why days with
        nothing logged are absent rather than zero.
        """
        with database.SessionLocal() as session:
            rows = session.execute(
                DAILY_TOTALS_SQL, {"start": start, "end": end}
            ).all()
            return [self._totals(row) for row in rows]

    def day(self, date: str) -> dict:
        """Totals and entries for one day, read together.

        One query pair rather than two endpoints, so the running total on
        screen cannot disagree with the list below it. Unlike `summary` this
        always returns a day: the page needs the kcal target before anything
        has been logged, which is exactly when it is most useful.
        """
        with database.SessionLocal() as session:
            row = session.execute(ONE_DAY_TOTALS_SQL, {"date": date}).one()
        return {
            "date": date,
            "totals": self._totals(row),
            "entries": self.get_by_date(date),
        }
