"""Food catalog and food log API endpoints."""

from fastapi import APIRouter, HTTPException, Query

from app.models.food import (
    Food,
    FoodCreate,
    FoodDay,
    FoodDaySummary,
    FoodLogCreate,
    FoodLogEntry,
    FoodUpdate,
)
from app.repositories.food_repo import FoodLogRepository, FoodRepository
from app.utils.date_helpers import get_current_date

router = APIRouter()


# `/day` and `/log` are declared before `/{food_id}` so neither is captured as
# a food id.
@router.get("/day", response_model=FoodDay)
def get_food_day(date: str | None = None):
    """Everything the food page needs for one day. Defaults to today."""
    return FoodLogRepository().day(date or get_current_date())


@router.get("/log", response_model=list[FoodLogEntry])
def get_food_log(date: str | None = None):
    """Entries for one day. Defaults to today."""
    return FoodLogRepository().get_by_date(date or get_current_date())


@router.get("/log/summary", response_model=list[FoodDaySummary])
def get_food_summary(start: str, end: str):
    """Daily kcal and macro totals over an inclusive date range.

    Days with nothing logged are absent rather than zero - an unlogged day and
    a fasted one are different facts, and reporting the first as the second
    would put a false zero on a chart.
    """
    return FoodLogRepository().summary(start, end)


@router.post("/log", response_model=FoodLogEntry, status_code=201)
def log_food(entry: FoodLogCreate):
    """Log a consumption event, by `food_id` or by naming the food."""
    if entry.food_id is None and entry.food is None:
        raise HTTPException(
            status_code=422, detail="Provide either food_id or food"
        )

    created = FoodLogRepository().create(entry)
    if created is None:
        raise HTTPException(status_code=404, detail="Food not found")
    return created


@router.delete("/log/{log_id}")
def delete_food_log(log_id: int):
    """Delete a logged entry."""
    if not FoodLogRepository().delete(log_id):
        raise HTTPException(status_code=404, detail="Log entry not found")
    return {"message": "Log entry deleted"}


@router.get("/", response_model=list[Food])
def search_foods(q: str | None = None, limit: int = Query(50, ge=1, le=500)):
    """Search the catalog by name or brand."""
    return FoodRepository().search(q, limit)


@router.post("/", response_model=Food, status_code=201)
def create_food(food: FoodCreate):
    """Create a food, or return the existing one with the same (name, brand)."""
    return FoodRepository().create(food)


@router.get("/{food_id}", response_model=Food)
def get_food(food_id: int):
    """Get one food."""
    food = FoodRepository().get_by_id(food_id)
    if food is None:
        raise HTTPException(status_code=404, detail="Food not found")
    return food


@router.put("/{food_id}", response_model=Food)
def update_food(food_id: int, changes: FoodUpdate):
    """Edit a food's macros.

    This is retroactive: totals are derived from the food at read time, so
    every past entry using it changes too. That is intended - it means fixing a
    wrong calorie count fixes history rather than leaving it wrong.
    """
    updated = FoodRepository().update(food_id, changes)
    if updated is None:
        raise HTTPException(status_code=404, detail="Food not found")
    return updated
