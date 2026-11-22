"""The library: blocks and programs, yours and built-in (plan 0022).

One listing over four sources - your blocks (presets), built-in blocks
(`app/presets/blocks/`), your programs (`workout_program`) and built-in
programs (`app/presets/*.liftoscript`) - plus reading and duplicating the
built-in blocks, and checking a script without generating it.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.upcoming import PRESETS
from app.models.preset import PresetItemCreate
from app.repositories.preset_repo import PresetNameTakenError, PresetRepository
from app.repositories.program_repo import ProgramRepository
from app.services.library_service import (
    BUILTIN_BLOCKS,
    block_script_to_items,
    builtin_block_script,
    resolve_block,
)
from app.services.liftoscript_service import LiftoscriptParseError, LiftoscriptParser

router = APIRouter()


class ScriptCheck(BaseModel):
    script: str
    num_cycles: int = Field(1, ge=1, le=52)


class BlockDuplicate(BaseModel):
    name: str | None = None


def _count_sets(script: str) -> int:
    try:
        return len(LiftoscriptParser().parse("## Block\n" + script, resolve_block=resolve_block))
    except LiftoscriptParseError:
        return 0


@router.get("/")
def get_library():
    """Everything in one listing, each entry saying whose it is."""
    my_blocks = [
        {"source": "mine", "id": p["doc_id"], "name": p["name"], "set_count": len(p["items"])}
        for p in PresetRepository().get_all()
    ]
    builtin_blocks = [
        {
            "source": "builtin",
            "key": key,
            "name": name,
            "set_count": _count_sets(builtin_block_script(name) or ""),
        }
        for key, name in BUILTIN_BLOCKS.items()
    ]
    my_programs = [
        {
            "source": "mine",
            "id": p["doc_id"],
            "name": p["name"],
            "built": p["builder"] is not None,
        }
        for p in ProgramRepository().get_all()
    ]
    builtin_programs = [
        {
            "source": "builtin",
            "key": key,
            "name": meta["display_name"],
            "description": meta["description"],
        }
        for key, meta in PRESETS.items()
    ]
    return {
        "blocks": my_blocks + builtin_blocks,
        "programs": my_programs + builtin_programs,
    }


@router.get("/blocks/builtin/{key}")
def get_builtin_block(key: str):
    name = BUILTIN_BLOCKS.get(key)
    if name is None:
        raise HTTPException(status_code=404, detail="Block not found")
    return {"key": key, "name": name, "script": builtin_block_script(name)}


@router.post("/blocks/builtin/{key}/duplicate", status_code=201)
def duplicate_builtin_block(key: str, payload: BlockDuplicate | None = None):
    """A built-in block as a block of yours, editable set by set."""
    name = BUILTIN_BLOCKS.get(key)
    if name is None:
        raise HTTPException(status_code=404, detail="Block not found")
    repo = PresetRepository()
    wanted = (payload.name if payload and payload.name else None) or f"{name} (mine)"
    taken = {p["name"].lower() for p in repo.get_all()}
    candidate, n = wanted, 2
    while candidate.lower() in taken:
        candidate = f"{wanted} {n}"
        n += 1
    try:
        preset = repo.create(candidate)
    except PresetNameTakenError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    for item in block_script_to_items(builtin_block_script(name) or ""):
        repo.add_item(preset["doc_id"], PresetItemCreate(**item))
    return repo.get_by_id(preset["doc_id"])


@router.post("/check")
def check_script(payload: ScriptCheck):
    """Parse a script, blocks and all, without touching the queue."""
    try:
        sets = LiftoscriptParser().parse(
            payload.script, payload.num_cycles, resolve_block=resolve_block
        )
    except LiftoscriptParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # the parser's own model validation
        raise HTTPException(status_code=400, detail=f"Failed to parse script: {exc}") from exc
    return {
        "sets": len(sets),
        "sessions": len({s.session for s in sets}),
        "mobility_sets": sum(1 for s in sets if s.is_mobility),
    }
