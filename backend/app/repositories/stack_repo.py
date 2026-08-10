"""Stack repository — named groups of consumables.

`database.SessionLocal` is reached through the module deliberately; see the
header of `food_repo.py`.
"""

from sqlalchemy import func, select, text

from app import database
from app.db.models import Food, FoodLog, Stack, StackItem
from app.models.stack import StackCreate, StackItemCreate, StackUpdate
from app.repositories.food_repo import FoodRepository, _entry
from app.utils.date_helpers import (
    format_timestamp,
    get_current_date,
    get_current_datetime,
)

# A stack counts as taken on a date when every one of its foods appears in that
# day's log. Derived rather than recorded: `food_log` carries no `stack_id`, on
# purpose (Plan 0011 §2), so this holds whether the button or manual entry put
# the rows there — and editing a stack cannot rewrite what a past day claims.
#
# An empty stack is never "taken": `MIN(...)` over no rows is NULL, and the
# outer COALESCE turns that into 0 rather than a vacuous true.
TAKEN_ON_SQL = text(
    """
    SELECT COALESCE(MIN(
        EXISTS (SELECT 1 FROM food_log fl
                 WHERE fl.food_id = si.food_id AND fl.date = :date)
    ), 0) AS taken
    FROM stack_item si
    WHERE si.stack_id = :stack_id
    """
)

# The most recent date on which it was taken, by the same definition. Bounded
# to dates the stack's foods actually appear on, so it stays cheap.
LAST_TAKEN_SQL = text(
    """
    SELECT MAX(fl.date) AS last_taken
    FROM (SELECT DISTINCT date FROM food_log) fl
    WHERE NOT EXISTS (
        SELECT 1 FROM stack_item si
         WHERE si.stack_id = :stack_id
           AND NOT EXISTS (SELECT 1 FROM food_log l
                            WHERE l.food_id = si.food_id AND l.date = fl.date)
    )
    AND EXISTS (SELECT 1 FROM stack_item si WHERE si.stack_id = :stack_id)
    """
)


class StackRepository:
    """Presets for logging several consumables at once."""

    @staticmethod
    def _serialize_item(item: StackItem, food: Food) -> dict:
        return {
            "doc_id": item.id,
            "food_id": food.id,
            "name": food.name,
            "brand": food.brand,
            "kind": food.kind,
            "serving_desc": food.serving_desc,
            "servings": item.servings,
            "order": item.order,
            "kcal_per_serving": food.kcal_per_serving,
        }

    def _serialize(self, session, stack: Stack, today: str) -> dict:
        items = session.execute(
            select(StackItem, Food)
            .join(Food, Food.id == StackItem.food_id)
            .where(StackItem.stack_id == stack.id)
            .order_by(StackItem.order)
        ).all()

        taken = session.execute(
            TAKEN_ON_SQL, {"stack_id": stack.id, "date": today}
        ).scalar_one()
        last = session.execute(LAST_TAKEN_SQL, {"stack_id": stack.id}).scalar_one()

        return {
            "doc_id": stack.id,
            "name": stack.name,
            "note": stack.note,
            "order": stack.order,
            "created_at": stack.created_at,
            "items": [self._serialize_item(item, food) for item, food in items],
            "taken_today": bool(taken),
            "last_taken": last,
        }

    def _replace_items(self, session, stack: Stack, items: list[StackItemCreate]) -> None:
        """Set the membership to exactly `items`.

        Wholesale replacement, not a merge — see `StackUpdate`. Existing rows
        are deleted first so an item dropped from the list actually leaves.
        """
        foods = FoodRepository()
        session.query(StackItem).filter(StackItem.stack_id == stack.id).delete()
        session.flush()

        seen: set[int] = set()
        order = 0
        for entry in items:
            if entry.food_id is not None:
                food = session.get(Food, entry.food_id)
                if food is None:
                    raise LookupError(f"food {entry.food_id} does not exist")
            else:
                food = foods.resolve(session, entry.food)

            # UNIQUE (stack_id, food_id) would reject a repeat anyway; catching
            # it here means the caller gets one clear error rather than an
            # IntegrityError naming a constraint they cannot see.
            if food.id in seen:
                raise ValueError(f"'{food.name}' appears twice in the stack")
            seen.add(food.id)

            order += 1
            session.add(
                StackItem(
                    stack_id=stack.id,
                    food_id=food.id,
                    servings=entry.servings,
                    order=order,
                )
            )
        session.flush()

    def get_all(self) -> list[dict]:
        today = get_current_date()
        with database.SessionLocal() as session:
            stacks = (
                session.execute(select(Stack).order_by(Stack.order, Stack.name))
                .scalars()
                .all()
            )
            return [self._serialize(session, stack, today) for stack in stacks]

    def get_by_id(self, stack_id: int) -> dict | None:
        with database.SessionLocal() as session:
            stack = session.get(Stack, stack_id)
            if stack is None:
                return None
            return self._serialize(session, stack, get_current_date())

    def create(self, payload: StackCreate) -> dict:
        with database.SessionLocal() as session:
            next_order = (
                session.execute(select(func.coalesce(func.max(Stack.order), 0))).scalar_one()
                + 1
            )
            stack = Stack(
                name=payload.name,
                note=payload.note,
                order=next_order,
                created_at=format_timestamp(get_current_datetime()),
            )
            session.add(stack)
            session.flush()
            self._replace_items(session, stack, payload.items)
            session.commit()
            return self._serialize(session, stack, get_current_date())

    def update(self, stack_id: int, changes: StackUpdate) -> dict | None:
        with database.SessionLocal() as session:
            stack = session.get(Stack, stack_id)
            if stack is None:
                return None

            fields = changes.model_dump(exclude_unset=True)
            items = fields.pop("items", None)
            for field, value in fields.items():
                setattr(stack, field, value)
            if items is not None:
                self._replace_items(
                    session, stack, [StackItemCreate(**i) for i in items]
                )

            session.commit()
            return self._serialize(session, stack, get_current_date())

    def delete(self, stack_id: int) -> bool:
        """Delete a stack and its membership.

        `stack_item` goes by cascade. The `food` rows and every past `food_log`
        row stay — they are history, and the stack never owned them.
        """
        with database.SessionLocal() as session:
            stack = session.get(Stack, stack_id)
            if stack is None:
                return False
            session.delete(stack)
            session.commit()
            return True

    def log(self, stack_id: int, consumed_at: str | None = None) -> dict | None:
        """Write one `food_log` row per item, all at the same instant.

        One transaction: a stack half-logged is worse than not logged, because
        the missing half is invisible.

        Nothing records that these rows came from a stack. That is the point —
        the log says what was consumed, and the stack is only how it was
        entered (Plan 0011 §2).
        """
        with database.SessionLocal() as session:
            stack = session.get(Stack, stack_id)
            if stack is None:
                return None

            when = consumed_at or format_timestamp(get_current_datetime())
            now = format_timestamp(get_current_datetime())

            rows = session.execute(
                select(StackItem, Food)
                .join(Food, Food.id == StackItem.food_id)
                .where(StackItem.stack_id == stack_id)
                .order_by(StackItem.order)
            ).all()

            written = []
            for item, food in rows:
                log = FoodLog(
                    consumed_at=when,
                    food_id=food.id,
                    servings=item.servings,
                    # Deliberately no meal. Swallowing omega at 7am is not
                    # breakfast, and filing it as one would inflate a meal's
                    # calories with things nobody ate.
                    meal=None,
                    created_at=now,
                )
                session.add(log)
                session.flush()
                written.append(_entry(log, food))

            session.commit()
            return {"stack": stack.name, "consumed_at": when, "entries": written}
