"""Saved programs (plan 0022). `database.SessionLocal` through the module; see
`food_repo.py`."""

import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import database
from app.db.models import WorkoutProgram
from app.models.program import ProgramCreate, ProgramUpdate
from app.utils.date_helpers import get_current_datetime


class ProgramNameTakenError(ValueError):
    pass


class ProgramRepository:
    @staticmethod
    def _serialize(program: WorkoutProgram) -> dict:
        return {
            "doc_id": program.id,
            "name": program.name,
            "script": program.script,
            "builder": json.loads(program.builder) if program.builder else None,
            "created_at": program.created_at,
            "updated_at": program.updated_at,
        }

    def get_all(self) -> list[dict]:
        with database.SessionLocal() as session:
            rows = session.execute(select(WorkoutProgram).order_by(WorkoutProgram.name)).scalars()
            return [self._serialize(p) for p in rows]

    def get_by_id(self, program_id: int) -> dict | None:
        with database.SessionLocal() as session:
            program = session.get(WorkoutProgram, program_id)
            return self._serialize(program) if program else None

    def get_by_name(self, name: str) -> dict | None:
        with database.SessionLocal() as session:
            program = session.execute(
                select(WorkoutProgram).where(WorkoutProgram.name == name)
            ).scalar_one_or_none()
            return self._serialize(program) if program else None

    def create(self, payload: ProgramCreate) -> dict:
        now = get_current_datetime()
        with database.SessionLocal() as session:
            program = WorkoutProgram(
                name=payload.name,
                script=payload.script,
                builder=json.dumps(payload.builder) if payload.builder is not None else None,
                created_at=now,
                updated_at=now,
            )
            session.add(program)
            try:
                session.commit()
            except IntegrityError as exc:
                raise ProgramNameTakenError(
                    f"A program named '{payload.name}' already exists"
                ) from exc
            session.refresh(program)
            return self._serialize(program)

    def update(self, program_id: int, changes: ProgramUpdate) -> dict | None:
        sent = changes.model_fields_set
        with database.SessionLocal() as session:
            program = session.get(WorkoutProgram, program_id)
            if program is None:
                return None
            if "name" in sent and changes.name is not None:
                program.name = changes.name
            if "script" in sent and changes.script is not None:
                program.script = changes.script
                # A script without its builder model is a hand edit: the
                # builder cannot read it back, so it lets go.
                if "builder" not in sent:
                    program.builder = None
            if "builder" in sent:
                program.builder = (
                    json.dumps(changes.builder) if changes.builder is not None else None
                )
            program.updated_at = get_current_datetime()
            try:
                session.commit()
            except IntegrityError as exc:
                raise ProgramNameTakenError(
                    f"A program named '{changes.name}' already exists"
                ) from exc
            session.refresh(program)
            return self._serialize(program)

    def delete(self, program_id: int) -> bool:
        with database.SessionLocal() as session:
            program = session.get(WorkoutProgram, program_id)
            if program is None:
                return False
            session.delete(program)
            session.commit()
            return True
