"""Saved program models - programs of yours, as script (plan 0022)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _clean_name(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("A program needs a name")
    return value


class ProgramCreate(BaseModel):
    name: str
    script: str = ""
    #: The program builder's model, when the builder wrote `script`.
    builder: dict[str, Any] | None = None

    _clean = field_validator("name")(_clean_name)


class ProgramUpdate(BaseModel):
    """Every field optional. Sending `script` without `builder` is a hand edit
    and detaches the builder; send both to keep them together."""

    name: str | None = None
    script: str | None = None
    builder: dict[str, Any] | None = None

    _clean = field_validator("name")(_clean_name)


class Program(BaseModel):
    id: int = Field(..., alias="doc_id")
    name: str
    script: str
    builder: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)
