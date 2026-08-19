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


class ExerciseCreate(ExerciseBase):
    """Model for creating an exercise."""
    notes: str | None = None
    # Bounded here *and* by a CHECK: the agent writes raw SQL and never passes
    # through Pydantic (ADR-0002), so the constraint is the rule both obey.
    rating: int | None = Field(None, ge=1, le=5)


class ExerciseUpdate(BaseModel):
    """Model for updating an exercise.

    Every field is optional and absence means "leave it alone". `rating` is the
    one where that is not enough — clearing a rating back to unrated is a real
    edit — so the repository distinguishes an omitted field from an explicit
    null via `model_fields_set` rather than treating both as no-op.
    """
    name: str | None = None
    category: str | None = None
    notes: str | None = None
    rating: int | None = Field(None, ge=1, le=5)


class Exercise(ExerciseBase):
    """Full exercise model with metadata."""
    id: int = Field(..., alias="doc_id")
    notes: str | None = None
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
