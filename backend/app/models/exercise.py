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
    pass


class ExerciseUpdate(BaseModel):
    """Model for updating an exercise."""
    name: str | None = None
    category: str | None = None


class Exercise(ExerciseBase):
    """Full exercise model with metadata."""
    id: int = Field(..., alias="doc_id")
    last_used: str | None = None
    use_count: int = 0
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class ExercisesByCategoryResponse(BaseModel):
    """Response for exercises grouped by category."""
    category: str
    exercises: list[str]
