"""Note repository.

`database.SessionLocal` is reached through the module deliberately - see the
header of `food_repo.py`.
"""

from sqlalchemy import func, select, text

from app import database
from app.db.models import Note
from app.models.note import NoteCreate
from app.utils.date_helpers import format_timestamp, get_current_datetime

# The journal review query from Plan 0005 §1a: notes and documents side by
# side, so a `kind` accumulating steadily over a long history is visible as a
# shape asking to be formalised. `document` kinds are prefixed so the two
# namespaces stay distinguishable in one list.
JOURNAL_REVIEW_SQL = text(
    """
    SELECT COALESCE(kind, '(none)') AS kind, COUNT(*) AS n,
           MIN(date) AS first, MAX(date) AS last
    FROM note GROUP BY kind
    UNION ALL
    SELECT 'doc:' || kind, COUNT(*), MIN(imported_at), MAX(imported_at)
    FROM document GROUP BY kind
    ORDER BY n DESC
    """
)


class NoteRepository:
    """Prose observations, the unshaped half of the journal."""

    @staticmethod
    def _serialize(note: Note) -> dict:
        return {
            "doc_id": note.id,
            "noted_at": note.noted_at,
            "date": note.date,
            "kind": note.kind,
            "body": note.body,
            "source": note.source,
        }

    def get_all(
        self,
        kind: str | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Most recent first, optionally filtered by kind and date range."""
        with database.SessionLocal() as session:
            stmt = select(Note).order_by(Note.noted_at.desc())
            if kind:
                stmt = stmt.where(Note.kind == kind)
            if start:
                stmt = stmt.where(Note.date >= start)
            if end:
                stmt = stmt.where(Note.date <= end)
            notes = session.execute(stmt.limit(limit)).scalars().all()
            return [self._serialize(n) for n in notes]

    def get_by_id(self, note_id: int) -> dict | None:
        with database.SessionLocal() as session:
            note = session.get(Note, note_id)
            return self._serialize(note) if note else None

    def create(self, note: NoteCreate) -> dict:
        with database.SessionLocal() as session:
            created = Note(
                noted_at=note.noted_at or format_timestamp(get_current_datetime()),
                kind=note.kind,
                body=note.body,
                source=note.source,
            )
            session.add(created)
            session.commit()
            session.refresh(created)
            return self._serialize(created)

    def delete(self, note_id: int) -> bool:
        """Notes are deletable. The journal is staging, not the audit log.

        Plan 0005 §1a: the audit log's value is that nothing can rewrite it;
        the journal's value is that its contents *will* be restructured. A
        mistaken note that can never be removed is the reason the two are
        separate tables.
        """
        with database.SessionLocal() as session:
            note = session.get(Note, note_id)
            if note is None:
                return False
            session.delete(note)
            session.commit()
            return True

    def kinds(self) -> list[dict]:
        """Counts and date spans per kind, across notes and documents."""
        with database.SessionLocal() as session:
            rows = session.execute(JOURNAL_REVIEW_SQL).all()
            return [
                {
                    "kind": row.kind,
                    "count": row.n,
                    "first": row.first,
                    "last": row.last,
                }
                for row in rows
            ]

    def count(self) -> int:
        with database.SessionLocal() as session:
            return session.execute(select(func.count(Note.id))).scalar_one()
