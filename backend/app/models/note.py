"""Note data models."""

from pydantic import BaseModel, ConfigDict, Field


class NoteCreate(BaseModel):
    """Model for creating a note.

    `kind` is free text on purpose - 'intention', 'review', 'workout',
    'injury', and whatever the coaching loop grows next. Constraining it would
    mean a migration per note type.
    """

    body: str = Field(..., min_length=1)
    kind: str | None = None
    noted_at: str | None = None
    # Who observed this. Defaults to 'manual'; the agent passes its own name,
    # so "did I write this or did a model infer it?" stays answerable.
    source: str = "manual"


class Note(BaseModel):
    """A note as stored."""

    id: int = Field(..., alias="doc_id")
    noted_at: str
    date: str
    kind: str | None = None
    body: str
    source: str

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class NoteKindSummary(BaseModel):
    """One row of the journal review query (Plan 0005 §1a).

    The failure mode for a landing zone is silt: rows nobody revisits. A `kind`
    accumulating steadily over a long history is a shape asking to be
    formalised, and this is what makes that visible.
    """

    kind: str
    count: int
    first: str | None = None
    last: str | None = None
