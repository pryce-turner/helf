"""Body composition API endpoints."""

import logging
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from fastapi import Query as QueryParam

import app.database as database
from app.models.body_composition import (
    BodyComposition,
    BodyCompositionCreate,
    BodyCompositionStats,
    BodyCompositionSyncResult,
    BodyCompositionTrend,
    ScaleSyncRequest,
    ScaleSyncResult,
)
from app.repositories.body_comp_repo import BodyCompositionRepository
from app.services import bodyspec_sync
from app.services.bodyspec_client import (
    BodySpecAuthError,
    BodySpecClient,
    BodySpecError,
)
from app.utils.date_helpers import get_current_datetime

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=list[BodyComposition])
def get_measurements(
    start_date: str | None = None,
    end_date: str | None = None,
    skip: int = 0,
    limit: int = 100,
    sort: Literal["observed", "ingested"] = "observed",
):
    """Get body composition measurements.

    `sort` chooses which timestamp orders the result, and the two answer
    different questions. `observed` is when the weighing happened - what a
    chart wants. `ingested` is when the row was written - what you want when
    hunting a bad row, because a scale with a wrong clock files a reading taken
    today under a date years away and it is invisible in observed order.

    Ignored when a date range is given: that query is about when measurements
    happened by definition.
    """
    repo = BodyCompositionRepository()

    if start_date and end_date:
        return repo.get_by_date_range(start_date, end_date)

    return repo.get_all(skip=skip, limit=limit, sort=sort)


@router.get("/latest", response_model=BodyComposition | None)
def get_latest_measurement():
    """Get the most recent measurement."""
    repo = BodyCompositionRepository()
    latest = repo.get_latest()

    if not latest:
        raise HTTPException(status_code=404, detail="No measurements found")

    return latest


@router.get("/stats", response_model=BodyCompositionStats)
def get_stats():
    """Get summary statistics."""
    repo = BodyCompositionRepository()
    return repo.get_stats()


@router.get("/trends", response_model=BodyCompositionTrend)
def get_trends(
    days: int = QueryParam(30, ge=1, le=365, description="Number of days"),
    source: str | None = QueryParam(
        None,
        description=(
            "Restrict to one instrument, e.g. 'openscale' or 'bodyspec'. "
            "Omit to receive every point with `sources` naming each one - a "
            "chart must not join points from different instruments with a line."
        ),
    ),
):
    """Get trend data for charts."""
    repo = BodyCompositionRepository()
    measurements = repo.get_recent(days=days, source=source)

    dates = []
    weights = []
    body_fat_pcts = []
    muscle_masses = []
    water_pcts = []
    sources = []

    for m in measurements:
        dates.append(m.get('date', ''))
        weights.append(m.get('weight'))
        body_fat_pcts.append(m.get('body_fat_pct'))
        muscle_masses.append(m.get('muscle_mass'))
        water_pcts.append(m.get('water_pct'))
        sources.append(m.get('source', ''))

    return BodyCompositionTrend(
        dates=dates,
        weights=weights,
        body_fat_pcts=body_fat_pcts,
        muscle_masses=muscle_masses,
        water_pcts=water_pcts,
        sources=sources,
    )


@router.post("/", response_model=BodyComposition, status_code=201)
def create_measurement(measurement: BodyCompositionCreate):
    """Create a new measurement (manual entry)."""
    repo = BodyCompositionRepository()
    created = repo.create(measurement)

    if not created:
        raise HTTPException(
            status_code=409,
            detail="Measurement with this timestamp already exists"
        )

    return created


@router.post("/sync/scale", response_model=ScaleSyncResult)
def sync_scale(payload: ScaleSyncRequest):
    """Drain the scale's onboard memory into helf.

    Separate from `POST /` for one reason that is easy to miss: that route
    calls `repo.create(measurement)` with no `source`, so it writes
    `source='manual'`, and `BodyCompositionCreate` has no `source` field to
    override it with. Posting drained readings through it would file every one
    as hand entry - silently, because a manual entry is a legitimate thing for
    that route to produce - and split the openScale series at an arbitrary
    date.

    The source is therefore fixed **by the route**, not taken from the client.
    It stays `openscale` because `observation.source` names the *instrument*,
    and the instrument has not changed: the same BF720, the same bioimpedance
    estimate, the same known disagreement with DEXA that
    `BodyCompositionStats.primary_source` exists to keep honest. The name reads
    like the Android app that is being removed; a split would be worse than a
    slightly wrong name.

    Duplicate rejection stays in the database. `create()` returns None when
    `(observed_at, source)` collides, which has been the real guard since plan
    0010, so a replayed reading costs one SELECT and writes nothing.
    """
    repo = BodyCompositionRepository()

    imported = 0
    skipped = 0
    for reading in payload.readings:
        if repo.create(reading, source="openscale"):
            imported += 1
        else:
            skipped += 1

    logger.info(
        "Scale drain: %d received, %d imported, %d already held",
        len(payload.readings),
        imported,
        skipped,
    )
    return ScaleSyncResult(
        readings_received=len(payload.readings),
        imported=imported,
        skipped=skipped,
    )


@router.post("/sync/bodyspec", response_model=BodyCompositionSyncResult)
def sync_bodyspec(authorization: str = Header(...)):
    """Import DEXA scans from BodySpec.

    The access token arrives in the `Authorization` header, is forwarded
    upstream, and is never written anywhere - not to `helf.db`, not to config,
    not to a log. It exists inside Helf for the duration of this request. See
    docs/plans/0008-bodyspec-integration.md §3 for why that is the whole
    design rather than a precaution.

    Sync is user-triggered. There is no scheduler and no stored credential, so
    there is nothing to rotate, leak, or find expired with nobody present.
    """
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=401,
            detail="Expected `Authorization: Bearer <bodyspec access token>`.",
        )

    try:
        result = bodyspec_sync.sync(
            client=BodySpecClient(),
            token=token,
            # Resolved through the module rather than imported by name, so the
            # test fixture's patched sessionmaker is picked up. A `from ...
            # import SessionLocal` here binds the production engine at import
            # time and needs a matching entry in conftest's patch list to be
            # safe - and a test that misses it writes to the real database.
            session_factory=database.SessionLocal,
            created_at=get_current_datetime(),
        )
    except BodySpecAuthError as exc:
        # The one error the user will actually hit. A generic 500 here would
        # send them debugging Helf instead of pasting a new token.
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except BodySpecError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    logger.info(
        "BodySpec sync: %s found, %s imported, %s skipped, %s metrics",
        result["scans_found"],
        result["imported"],
        result["skipped"],
        result["metrics_written"],
    )
    return result


@router.delete("/{measurement_id}", status_code=204)
def delete_measurement(measurement_id: int):
    """Delete a measurement."""
    repo = BodyCompositionRepository()
    deleted = repo.delete(measurement_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Measurement not found")
