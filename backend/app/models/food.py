"""Food catalog and food log data models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Meal = Literal["breakfast", "lunch", "dinner", "snack"]
FoodKind = Literal["food", "supplement"]


class FoodBase(BaseModel):
    """Macros for one serving of a food."""

    name: str = Field(..., min_length=1)
    # Empty string, never None: SQLite treats NULLs as distinct in a UNIQUE
    # index, so a nullable brand would make UNIQUE (name, brand) decorative and
    # let unlimited duplicate ('Chicken', NULL) rows accumulate.
    brand: str = ""
    # A supplement is stored here too - it is a thing with a serving size that
    # you swallow at a time. `kind` is what keeps a vitamin out of the meal
    # list and out of the missing-macros warning.
    kind: FoodKind = "food"
    serving_desc: str | None = None
    kcal_per_serving: float | None = Field(None, ge=0)
    protein_g: float | None = Field(None, ge=0)
    carb_g: float | None = Field(None, ge=0)
    fat_g: float | None = Field(None, ge=0)

    @field_validator("brand", mode="before")
    @classmethod
    def brand_never_null(cls, value: str | None) -> str:
        """Accept a null brand from a client and store it as ''."""
        return "" if value is None else value


class FoodCreate(FoodBase):
    """Model for creating a food."""


class FoodUpdate(BaseModel):
    """Model for editing a food. Every field optional; omitted fields are kept.

    Editing macros rewrites every past log entry's totals, because a serving's
    numbers are derived rather than stored (Plan 0005 §1). That is the intended
    behaviour - it means a correction is retroactive - but it is why this is a
    deliberate PUT rather than something the log endpoint does implicitly.
    """

    name: str | None = Field(None, min_length=1)
    brand: str | None = None
    kind: FoodKind | None = None
    serving_desc: str | None = None
    kcal_per_serving: float | None = Field(None, ge=0)
    protein_g: float | None = Field(None, ge=0)
    carb_g: float | None = Field(None, ge=0)
    fat_g: float | None = Field(None, ge=0)


class Food(FoodBase):
    """A food as stored."""

    id: int = Field(..., alias="doc_id")
    created_at: str

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class FoodLogCreate(BaseModel):
    """Model for logging a consumption event.

    Either name an existing food by `food_id`, or give a `food` to resolve by
    `(name, brand)` - creating it when new. The second form is what the agent's
    `log_food` tool does, and what a UI does when the user types a food that
    isn't in the catalog yet.
    """

    food_id: int | None = None
    food: FoodCreate | None = None
    servings: float = Field(1.0, gt=0)
    meal: Meal | None = None
    consumed_at: str | None = None


class FoodLogEntry(BaseModel):
    """A logged consumption event with the food's macros resolved onto it.

    The macro fields are `servings x` the food's per-serving numbers, computed
    at read time. They are not stored, so correcting a food corrects history.
    """

    id: int = Field(..., alias="doc_id")
    consumed_at: str
    date: str
    servings: float
    meal: Meal | None = None
    food_id: int
    name: str
    brand: str
    kind: FoodKind = "food"
    serving_desc: str | None = None
    kcal: float | None = None
    protein_g: float | None = None
    carb_g: float | None = None
    fat_g: float | None = None

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class FoodDaySummary(BaseModel):
    """Totals for one day.

    `foods_missing_macros` exists because the totals COALESCE NULL macros to
    zero. Without it a day containing one food with unknown protein reports a
    protein total that is simply too low, with nothing on screen to say so.

    `kcal_target` is the day's Katch-McArdle RMR times the activity multiplier,
    carried forward from the last DEXA scan on or before it (Plan 0008 §8). It
    is NULL before the first scan - there is no default to fall back on, and
    inventing one would put a target on screen that no measurement supports.
    """

    date: str
    kcal: float | None = None
    protein_g: float | None = None
    carb_g: float | None = None
    fat_g: float | None = None
    entries: int = 0
    foods_missing_macros: int = 0
    supplements_taken: int = 0
    kcal_target: float | None = None


class FoodDay(BaseModel):
    """Everything the food page needs for one day, in one request.

    Deliberately composite rather than three endpoints: the totals and the
    entries are read from the same instant, so the running total on screen can
    never disagree with the list underneath it.
    """

    date: str
    totals: FoodDaySummary
    entries: list[FoodLogEntry]
