"""Exercise and category API endpoints."""

from fastapi import APIRouter, HTTPException

from app.models.exercise import (
    Exercise,
    ExerciseCreate,
    ExerciseUpdate,
    Category,
    CategoryCreate,
    ExercisesByCategoryResponse,
    SeedExercisesResponse,
)
from app.repositories.exercise_repo import ExerciseRepository, CategoryRepository

# Exercises from workout presets (wendler_531, stronglifts_5x5)
PRESET_EXERCISES = {
    "Legs": [
        "Barbell Squat",
        "Front Squat",
        "Bulgarian Split Squat",
    ],
    "Push": [
        "Flat Barbell Bench Press",
        "Incline Dumbbell Press",
        "Overhead Press",
        "Parallel Bar Triceps Dip",
    ],
    "Pull": [
        "Deadlift",
        "Pull-ups",
        "Dumbbell Row",
        "Barbell Row",
    ],
    "Core": [
        "Decline Crunch",
        "Landmines",
        "Cable side bend",
    ],
}

router = APIRouter()


# Exercise endpoints
@router.get("/", response_model=list[Exercise])
def get_exercises():
    """Get all exercises."""
    repo = ExerciseRepository()
    return repo.get_all()


@router.get("/recent", response_model=list[Exercise])
def get_recent_exercises(limit: int = 10):
    """Get recently used exercises."""
    repo = ExerciseRepository()
    return repo.get_recent(limit=limit)


@router.get("/{exercise_name}", response_model=Exercise)
def get_exercise(exercise_name: str):
    """Get a specific exercise by name."""
    repo = ExerciseRepository()
    exercise = repo.get_by_name(exercise_name)

    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    return exercise


@router.post("/", response_model=Exercise, status_code=201)
def create_exercise(exercise: ExerciseCreate):
    """Create a new exercise."""
    repo = ExerciseRepository()
    return repo.create(exercise)


@router.put("/{exercise_id}", response_model=Exercise)
def update_exercise(exercise_id: int, exercise: ExerciseUpdate):
    """Update an exercise."""
    repo = ExerciseRepository()
    updated = repo.update(exercise_id, exercise)

    if not updated:
        raise HTTPException(status_code=404, detail="Exercise not found")

    return updated


@router.delete("/{exercise_id}", status_code=204)
def delete_exercise(exercise_id: int):
    """Delete an exercise."""
    repo = ExerciseRepository()
    if not repo.delete(exercise_id):
        raise HTTPException(status_code=404, detail="Exercise not found")


@router.post("/seed", response_model=SeedExercisesResponse)
def seed_exercises():
    """Seed exercises from workout presets.

    Creates all exercises needed for the built-in workout programs
    (Wendler 5/3/1, StrongLifts 5x5). Only creates exercises that
    don't already exist.
    """
    exercise_repo = ExerciseRepository()
    category_repo = CategoryRepository()

    created_categories = 0
    created_exercises = 0

    for category_name, exercises in PRESET_EXERCISES.items():
        # Get or create category
        category = category_repo.get_by_name(category_name)
        if not category:
            category = category_repo.create(CategoryCreate(name=category_name))
            created_categories += 1

        # Create exercises that don't exist
        for exercise_name in exercises:
            existing = exercise_repo.get_by_name(exercise_name)
            if not existing:
                exercise_repo.create(ExerciseCreate(
                    name=exercise_name,
                    category=category_name,
                ))
                created_exercises += 1

    if created_exercises == 0 and created_categories == 0:
        message = "All preset exercises already exist"
    else:
        message = f"Created {created_exercises} exercises in {created_categories} categories"

    return SeedExercisesResponse(
        categories_created=created_categories,
        exercises_created=created_exercises,
        message=message,
    )


# Category endpoints
@router.get("/categories/", response_model=list[Category])
def get_categories():
    """Get all categories."""
    repo = CategoryRepository()
    return repo.get_all()


@router.get("/categories/{category_name}", response_model=Category)
def get_category(category_name: str):
    """Get a specific category by name."""
    repo = CategoryRepository()
    category = repo.get_by_name(category_name)

    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    return category


@router.post("/categories/", response_model=Category, status_code=201)
def create_category(category: CategoryCreate):
    """Create a new category."""
    repo = CategoryRepository()
    return repo.create(category)


@router.get("/categories/{category_name}/exercises", response_model=ExercisesByCategoryResponse)
def get_exercises_by_category(category_name: str):
    """Get all exercises in a category."""
    exercise_repo = ExerciseRepository()
    exercises = exercise_repo.get_by_category(category_name)

    # Extract just the names
    exercise_names = [e['name'] for e in exercises]

    return ExercisesByCategoryResponse(
        category=category_name,
        exercises=exercise_names
    )
