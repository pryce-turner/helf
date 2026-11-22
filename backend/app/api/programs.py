"""Saved programs - programs of yours, as script (plan 0022)."""

from fastapi import APIRouter, HTTPException

from app.models.program import Program, ProgramCreate, ProgramUpdate
from app.repositories.program_repo import ProgramNameTakenError, ProgramRepository

router = APIRouter()

NOT_FOUND = "Program not found"


@router.get("/", response_model=list[Program])
def get_programs():
    return ProgramRepository().get_all()


@router.post("/", response_model=Program, status_code=201)
def create_program(payload: ProgramCreate):
    try:
        return ProgramRepository().create(payload)
    except ProgramNameTakenError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{program_id}", response_model=Program)
def get_program(program_id: int):
    program = ProgramRepository().get_by_id(program_id)
    if program is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return program


@router.put("/{program_id}", response_model=Program)
def update_program(program_id: int, payload: ProgramUpdate):
    try:
        program = ProgramRepository().update(program_id, payload)
    except ProgramNameTakenError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if program is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return program


@router.delete("/{program_id}", status_code=204)
def delete_program(program_id: int):
    if not ProgramRepository().delete(program_id):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
