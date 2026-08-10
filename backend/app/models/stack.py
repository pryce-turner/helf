"""Stack data models — named groups of consumables logged in one action."""

from pydantic import BaseModel, ConfigDict, Field

from app.models.food import FoodCreate, FoodLogEntry


class StackItemCreate(BaseModel):
    """One consumable in a stack.

    Either name an existing catalog entry by `food_id`, or give a `food` to
    resolve by `(name, brand)` — creating it when new, which is how a
    supplement gets into the catalog in the first place.

    `servings` belongs here rather than on the food: two omega capsules in the
    morning and one in the evening is the same product taken differently.
    """

    food_id: int | None = None
    food: FoodCreate | None = None
    servings: float = Field(1.0, gt=0)


class StackItem(BaseModel):
    """A stack member, with the food resolved onto it."""

    id: int = Field(..., alias="doc_id")
    food_id: int
    name: str
    brand: str
    kind: str
    # Free text: "1 softgel, 1000mg EPA". The page renders it beside
    # `servings` so "2 x 1000mg EPA" reads without needing a dose column.
    serving_desc: str | None = None
    servings: float
    order: int
    kcal_per_serving: float | None = None

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class StackCreate(BaseModel):
    """Model for creating a stack."""

    name: str = Field(..., min_length=1)
    note: str | None = None
    items: list[StackItemCreate] = []


class StackUpdate(BaseModel):
    """Model for editing a stack.

    Passing `items` **replaces** the membership wholesale rather than merging.
    A group of supplements is edited as a list — "these are the three things I
    take in the morning" — and a merge would make removing one require a
    separate call the UI has no natural place for.
    """

    name: str | None = Field(None, min_length=1)
    note: str | None = None
    order: int | None = None
    items: list[StackItemCreate] | None = None


class Stack(BaseModel):
    """A stack and its members.

    `taken_today` is computed, not stored: every one of this stack's foods
    appears in today's log. Deliberately derived from `food_log` rather than
    from a marker written by the log button, so it is true whether the stack
    was logged in one tap or the items entered by hand — and so that editing a
    stack cannot retroactively change what a past day claims.
    """

    id: int = Field(..., alias="doc_id")
    name: str
    note: str | None = None
    order: int
    created_at: str
    items: list[StackItem] = []
    taken_today: bool = False
    last_taken: str | None = None

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class StackLogRequest(BaseModel):
    """Log every item in a stack at one instant. Defaults to now."""

    consumed_at: str | None = None


class StackLogResult(BaseModel):
    """What the one-tap log actually wrote."""

    stack: str
    consumed_at: str
    entries: list[FoodLogEntry]
