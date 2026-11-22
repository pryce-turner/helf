"""Workout preset API — hand-built workouts applied to a day (plan 0020).

Not to be confused with `/api/upcoming/presets`, the Liftoscript program
templates that generate the upcoming queue.
"""

from fastapi import APIRouter, HTTPException

from app.models.preset import (
    Preset,
    PresetApply,
    PresetApplyResponse,
    PresetCreate,
    PresetItem,
    PresetItemCreate,
    PresetItemUpdate,
    PresetReorder,
    PresetUpdate,
)
from app.repositories.preset_repo import PresetNameTakenError, PresetRepository
from app.services.library_service import is_reserved_block_name, preset_to_script

router = APIRouter()

NOT_FOUND = "Preset not found"


@router.get("/", response_model=list[Preset])
def get_presets():
    """Every preset with its tiles, by name."""
    return PresetRepository().get_all()


@router.post("/", response_model=Preset, status_code=201)
def create_preset(payload: PresetCreate | None = None):
    """Create an empty preset. With no name it is "New preset", numbered if taken."""
    if payload and payload.name and is_reserved_block_name(payload.name):
        raise HTTPException(status_code=409, detail=f"'{payload.name}' is a built-in block's name")
    try:
        return PresetRepository().create(payload.name if payload else None)
    except PresetNameTakenError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{preset_id}", response_model=Preset)
def get_preset(preset_id: int):
    preset = PresetRepository().get_by_id(preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return preset


@router.get("/{preset_id}/script")
def get_preset_script(preset_id: int):
    """The block as script - what `[Its name]` puts into a program."""
    preset = PresetRepository().get_by_id(preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return {"name": preset["name"], "script": preset_to_script(preset)}


@router.put("/{preset_id}", response_model=Preset)
def rename_preset(preset_id: int, payload: PresetUpdate):
    if is_reserved_block_name(payload.name):
        raise HTTPException(status_code=409, detail=f"'{payload.name}' is a built-in block's name")
    try:
        preset = PresetRepository().rename(preset_id, payload.name)
    except PresetNameTakenError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if preset is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return preset


@router.delete("/{preset_id}", status_code=204)
def delete_preset(preset_id: int):
    """Delete a preset and its tiles. Days it was applied to are untouched."""
    if not PresetRepository().delete(preset_id):
        raise HTTPException(status_code=404, detail=NOT_FOUND)


@router.post("/{preset_id}/items", response_model=PresetItem, status_code=201)
def add_preset_item(preset_id: int, payload: PresetItemCreate):
    item = PresetRepository().add_item(preset_id, payload)
    if item is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return item


@router.put("/items/{item_id}", response_model=PresetItem)
def update_preset_item(item_id: int, payload: PresetItemUpdate):
    item = PresetRepository().update_item(item_id, payload)
    if item is None:
        raise HTTPException(status_code=404, detail="Preset item not found")
    return item


@router.delete("/items/{item_id}", status_code=204)
def delete_preset_item(item_id: int):
    if not PresetRepository().delete_item(item_id):
        raise HTTPException(status_code=404, detail="Preset item not found")


@router.patch("/{preset_id}/reorder")
def reorder_preset(preset_id: int, payload: PresetReorder):
    if PresetRepository().reorder(preset_id, payload.item_ids) is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return {"message": "Preset reordered"}


@router.post("/{preset_id}/apply", response_model=PresetApplyResponse, status_code=201)
def apply_preset(preset_id: int, payload: PresetApply):
    """Copy the preset's tiles onto a date as planned sets, after the day's own."""
    count = PresetRepository().apply(preset_id, payload.date)
    if count is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    if count == 0:
        raise HTTPException(
            status_code=422, detail="This preset has no sets, so there is nothing to apply."
        )
    return {
        "preset_id": preset_id,
        "date": payload.date,
        "count": count,
        "message": f"Applied {count} set{'s' if count != 1 else ''} to {payload.date}",
    }
