"""Note API endpoints."""

from fastapi import APIRouter, HTTPException, Query

from app.models.note import Note, NoteCreate, NoteKindSummary
from app.repositories.note_repo import NoteRepository

router = APIRouter()


@router.get("/", response_model=list[Note])
def get_notes(
    kind: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
):
    """Notes, most recent first."""
    return NoteRepository().get_all(kind=kind, start=start, end=end, limit=limit)


@router.get("/kinds", response_model=list[NoteKindSummary])
def get_note_kinds():
    """Counts and date spans per kind, across notes and imported documents.

    The journal review query from Plan 0005 §1a. Worth reading occasionally: a
    kind with a long history and steady accumulation is a shape that has earned
    a real schema.
    """
    return NoteRepository().kinds()


@router.post("/", response_model=Note, status_code=201)
def create_note(note: NoteCreate):
    """Write a note."""
    return NoteRepository().create(note)


@router.get("/{note_id}", response_model=Note)
def get_note(note_id: int):
    """Get one note."""
    note = NoteRepository().get_by_id(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@router.delete("/{note_id}")
def delete_note(note_id: int):
    """Delete a note."""
    if not NoteRepository().delete(note_id):
        raise HTTPException(status_code=404, detail="Note not found")
    return {"message": "Note deleted"}
