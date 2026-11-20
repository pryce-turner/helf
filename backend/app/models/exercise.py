"""Exercise and category data models."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CategoryBase(BaseModel):
    """Base category model."""
    name: str = Field(..., min_length=1)


class CategoryCreate(CategoryBase):
    """Model for creating a category."""
    pass


class Category(CategoryBase):
    """Full category model with metadata."""
    id: int = Field(..., alias="doc_id")
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class ExerciseBase(BaseModel):
    """Base exercise model."""
    name: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)


class ExerciseFieldConfig(BaseModel):
    """The four field groups a set tile for this movement can offer.

    Shared by create, update and response so the bounds live in exactly one
    place. Bounded here *and* by named CHECKs: the agent writes raw SQL and
    never passes through Pydantic (ADR-0002), so the constraint is the rule
    both writers obey.

    An enabled group with a NULL default offers the input and leaves it
    blank. Disabling a group keeps its defaults stored, so re-enabling does
    not erase the configuration — the flag and the defaults are edited
    independently.
    """

    movement_break_enabled: bool = False
    reps_enabled: bool = True
    default_reps: int | None = Field(None, ge=1, le=500)
    weight_enabled: bool = True
    # Total pounds (ADR-0003). For a Farmer Carry: what is carried across
    # both hands, not per hand.
    default_weight_lb: float | None = Field(None, ge=0, le=2000)
    distance_enabled: bool = False
    default_distance: float | None = Field(None, ge=0, le=1000)
    default_distance_unit: str | None = Field(None, max_length=16)
    time_enabled: bool = False
    default_work_seconds: int | None = Field(None, ge=1, le=3600)
    default_rest_seconds: int | None = Field(None, ge=0, le=3600)
    default_rest_after_seconds: int | None = Field(None, ge=0, le=3600)


class ExerciseCreate(ExerciseBase, ExerciseFieldConfig):
    """Model for creating an exercise."""
    form: str | None = None
    application: str | None = None
    rating: int | None = Field(None, ge=1, le=5)


class ExerciseUpdate(BaseModel):
    """Model for updating an exercise.

    Every field is optional and absence means "leave it alone". The nullable
    fields are the ones where that is not enough — clearing a rating or a
    field default back to blank is a real edit — so the repository
    distinguishes an omitted field from an explicit null via
    `model_fields_set` rather than treating both as no-op.
    """
    name: str | None = None
    category: str | None = None
    form: str | None = None
    application: str | None = None
    rating: int | None = Field(None, ge=1, le=5)
    movement_break_enabled: bool | None = None
    reps_enabled: bool | None = None
    default_reps: int | None = Field(None, ge=1, le=500)
    weight_enabled: bool | None = None
    default_weight_lb: float | None = Field(None, ge=0, le=2000)
    distance_enabled: bool | None = None
    default_distance: float | None = Field(None, ge=0, le=1000)
    default_distance_unit: str | None = Field(None, max_length=16)
    time_enabled: bool | None = None
    default_work_seconds: int | None = Field(None, ge=1, le=3600)
    default_rest_seconds: int | None = Field(None, ge=0, le=3600)
    default_rest_after_seconds: int | None = Field(None, ge=0, le=3600)


class Exercise(ExerciseBase, ExerciseFieldConfig):
    """Full exercise model with metadata."""
    id: int = Field(..., alias="doc_id")
    form: str | None = None
    application: str | None = None
    rating: int | None = None
    last_used: str | None = None
    use_count: int = 0
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class ExercisesByCategoryResponse(BaseModel):
    """Response for exercises grouped by category."""
    category: str
    exercises: list[str]


class SeedExercisesResponse(BaseModel):
    """Response from seeding exercises."""
    categories_created: int
    exercises_created: int
    message: str
