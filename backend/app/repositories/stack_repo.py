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

# A stack counts as taken on a date when that day's log holds a **distinct
# entry** for every one of its foods, and no two stacks may claim the same
# entry. Derived rather than recorded: `food_log` carries no `stack_id`, on
# purpose (Plan 0011 §2), so this holds whether the button or manual entry put
# the rows there — and editing a stack cannot rewrite what a past day claims.
#
# The exclusivity is the part that took a bug to find. "Every food appears" is
# vacuously true for any stack whose foods are a **subset** of another's, so
# logging Morning (omega, cholestoff, D3, multi) marked Evening (omega,
# cholestoff) taken as well — a stack that had not been taken, reporting
# adherence that had not happened. Nothing about the subset is unusual; an
# evening dose being a shorter version of the morning one is the normal case.
#
# So entries are consumed rather than merely matched, and the stacks are
# offered the day's log most-specific-first: Morning takes one omega entry and
# one cholestoff entry off the table, and Evening then finds nothing left to
# claim unless a second dose was actually logged.
#
# Two properties worth keeping in mind:
#
# - **Entries, not servings.** A stack asking for 2 servings of omega is
#   satisfied by one logged entry of 1. Hand-entered rows do not carry the
#   preset's serving counts and never have; requiring the arithmetic to line up
#   would make "entered by hand" stop counting, which is the one thing this
#   derivation exists to support.
# - **Two identical doses are indistinguishable.** Logging Morning twice leaves
#   a spare omega and cholestoff entry, so Evening reads as taken. The log
#   genuinely does not say which dose was which, and the alternative — matching
#   on `consumed_at` groups — breaks hand entry, where the rows arrive minutes
#   apart. Over-reporting a repeated dose is the narrower error.
COUNTS_BY_DATE_SQL = text(
    """
    SELECT fl.date AS date, fl.food_id AS food_id, COUNT(*) AS n
      FROM food_log fl
     WHERE fl.food_id IN (SELECT food_id FROM stack_item)
     GROUP BY fl.date, fl.food_id
     ORDER BY fl.date DESC
    """
)


def _allocate(membership: list[tuple[int, list[int]]], supply: dict[int, int]) -> set[int]:
    """Which of `membership` one day's log can cover, each entry spent once.

    `membership` is (stack_id, food_ids) ordered most-specific-first. A stack
    that cannot be covered spends nothing — otherwise a half-matched Morning
    would eat the entries an Evening it contains is entitled to.

    An empty stack is never taken. `all()` over no foods is True, so the guard
    is explicit rather than falling out of the loop.
    """
    remaining = dict(supply)
    taken: set[int] = set()
    for stack_id, food_ids in membership:
        if not food_ids:
            continue
        if all(remaining.get(food_id, 0) > 0 for food_id in food_ids):
            for food_id in food_ids:
                remaining[food_id] -= 1
            taken.add(stack_id)
    return taken


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

    @staticmethod
    def _membership(session) -> list[tuple[int, list[int]]]:
        """Every stack's food ids, most specific first.

        Specificity is item count: a stack contained in another is offered the
        log second, so the larger one claims its entries first. Ties fall back
        to display order then id, so the answer does not depend on the order
        rows happen to come back in.

        The outer join keeps empty stacks in the list with no foods, which
        `_allocate` then skips — they exist and are simply never taken.
        """
        rows = session.execute(
            select(Stack.id, Stack.order, StackItem.food_id)
            .outerjoin(StackItem, StackItem.stack_id == Stack.id)
            .order_by(Stack.order, Stack.id, StackItem.order)
        ).all()

        foods: dict[int, list[int]] = {}
        order: dict[int, int] = {}
        for stack_id, stack_order, food_id in rows:
            foods.setdefault(stack_id, [])
            order[stack_id] = stack_order
            if food_id is not None:
                foods[stack_id].append(food_id)

        return sorted(
            foods.items(),
            key=lambda entry: (-len(entry[1]), order[entry[0]], entry[0]),
        )

    def _derive_taken(self, session, today: str) -> tuple[set[int], dict[int, str]]:
        """Which stacks are taken today, and the last date each was taken.

        Both answers come from the same allocation, run once per date. They
        have to: a `last_taken` computed by the looser "every food appears"
        rule would contradict `taken_today` on the very days the two disagree,
        and the contradiction would show up as a stack reading "not taken"
        above a "last taken: today".

        Dates are walked newest-first and the walk stops once every stack has
        an answer, so the usual case reads only the recent end of the log.
        """
        membership = self._membership(session)
        by_date: dict[str, dict[int, int]] = {}
        for date, food_id, count in session.execute(COUNTS_BY_DATE_SQL):
            by_date.setdefault(date, {})[food_id] = count

        taken_today = _allocate(membership, by_date.get(today, {}))

        last_taken: dict[int, str] = {}
        pending = {stack_id for stack_id, food_ids in membership if food_ids}
        for date in sorted(by_date, reverse=True):
            if not pending:
                break
            for stack_id in _allocate(membership, by_date[date]) & pending:
                last_taken[stack_id] = date
                pending.discard(stack_id)

        return taken_today, last_taken

    def _serialize(
        self,
        session,
        stack: Stack,
        taken_today: set[int],
        last_taken: dict[int, str],
    ) -> dict:
        items = session.execute(
            select(StackItem, Food)
            .join(Food, Food.id == StackItem.food_id)
            .where(StackItem.stack_id == stack.id)
            .order_by(StackItem.order)
        ).all()

        taken = stack.id in taken_today
        last = last_taken.get(stack.id)

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
            taken_today, last_taken = self._derive_taken(session, today)
            return [
                self._serialize(session, stack, taken_today, last_taken)
                for stack in stacks
            ]

    def get_by_id(self, stack_id: int) -> dict | None:
        with database.SessionLocal() as session:
            stack = session.get(Stack, stack_id)
            if stack is None:
                return None
            # Every stack, even to answer for one: whether this stack can claim
            # today's entries depends on which other stacks claimed them first.
            taken_today, last_taken = self._derive_taken(session, get_current_date())
            return self._serialize(session, stack, taken_today, last_taken)

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
            taken_today, last_taken = self._derive_taken(session, get_current_date())
            return self._serialize(session, stack, taken_today, last_taken)

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
            taken_today, last_taken = self._derive_taken(session, get_current_date())
            return self._serialize(session, stack, taken_today, last_taken)

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
