"""Exercise and category repository for database operations."""

from tinydb import Query
from datetime import datetime
from typing import Optional

from app.database import get_table, EXERCISES_TABLE, CATEGORIES_TABLE
from app.models.exercise import ExerciseCreate, CategoryCreate
from app.utils.date_helpers import get_current_datetime


class ExerciseRepository:
    """Repository for exercise data operations."""

    def __init__(self):
        self.table = get_table(EXERCISES_TABLE)
        self.query = Query()

    def get_all(self) -> list[dict]:
        """Get all exercises."""
        return self.table.all()

    def get_by_name(self, name: str) -> Optional[dict]:
        """Get an exercise by name."""
        results = self.table.search(self.query.name == name)
        return results[0] if results else None

    def get_by_category(self, category: str) -> list[dict]:
        """Get all exercises in a category."""
        exercises = self.table.search(self.query.category == category)
        # Sort by last_used descending (most recent first)
        exercises.sort(key=lambda x: x.get('last_used', ''), reverse=True)
        return exercises

    def create(self, exercise: ExerciseCreate) -> dict:
        """Create a new exercise."""
        # Check if exercise already exists
        existing = self.get_by_name(exercise.name)
        if existing:
            return existing

        now = get_current_datetime()
        exercise_dict = exercise.model_dump()
        exercise_dict['last_used'] = None
        exercise_dict['use_count'] = 0
        exercise_dict['created_at'] = now.isoformat()

        doc_id = self.table.insert(exercise_dict)
        return self.table.get(doc_id=doc_id)

    def update_usage(self, name: str, date: str) -> bool:
        """Update exercise usage statistics."""
        results = self.table.search(self.query.name == name)
        if not results:
            return False

        exercise = results[0]
        self.table.update({
            'last_used': date,
            'use_count': exercise.get('use_count', 0) + 1
        }, doc_ids=[exercise.doc_id])

        return True

    def get_recent(self, limit: int = 10) -> list[dict]:
        """Get recently used exercises."""
        exercises = self.table.all()
        # Filter out exercises without last_used
        exercises = [e for e in exercises if e.get('last_used')]
        # Sort by last_used descending
        exercises.sort(key=lambda x: x.get('last_used', ''), reverse=True)
        return exercises[:limit]


class CategoryRepository:
    """Repository for category data operations."""

    def __init__(self):
        self.table = get_table(CATEGORIES_TABLE)
        self.query = Query()

    def get_all(self) -> list[dict]:
        """Get all categories."""
        categories = self.table.all()
        # Sort alphabetically
        categories.sort(key=lambda x: x.get('name', ''))
        return categories

    def get_by_name(self, name: str) -> Optional[dict]:
        """Get a category by name."""
        results = self.table.search(self.query.name == name)
        return results[0] if results else None

    def create(self, category: CategoryCreate) -> dict:
        """Create a new category."""
        # Check if category already exists
        existing = self.get_by_name(category.name)
        if existing:
            return existing

        now = get_current_datetime()
        category_dict = category.model_dump()
        category_dict['created_at'] = now.isoformat()

        doc_id = self.table.insert(category_dict)
        return self.table.get(doc_id=doc_id)
