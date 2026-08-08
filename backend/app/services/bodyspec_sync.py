"""Import BodySpec DEXA scans into `document` and `metric`.

The shape of an import (docs/plans/0008-bodyspec-integration.md §5):

1. List every scan.
2. Skip any whose `result_id` is already a `document` - that is the whole of
   the idempotency story, and it is why a sync interrupted by an expired token
   is safely resumable.
3. Store the merged payload whole, then promote thirteen scalars from it.

Steps 2 and 3 happen in one transaction per scan: a document without its
metrics is a silent gap, and `metric.document_id` is what keeps provenance
intact.
"""

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, Metric, Observation
from app.services.bodyspec_client import BodySpecClient
from app.utils.date_helpers import parse_iso_timestamp
from app.utils.units import KG_TO_LB

logger = logging.getLogger(__name__)

DOCUMENT_KIND = "dexa_bodyspec"
SOURCE = "bodyspec"

# Katch-McArdle. Chosen over the four formulas BodySpec returns because it is
# driven by lean body mass, which is the thing a DEXA scan actually measures -
# Mifflin-St. Jeor needs only a bathroom scale and a birthday. BodySpec does
# not offer it, so it is computed here; their estimates stay in document.raw.
RMR_INTERCEPT = 370.0
RMR_PER_KG_FFM = 21.6

# fat + lean + bone should reconstruct total mass exactly. 50g of slack for
# float noise in the payload.
DECOMPOSITION_TOLERANCE_KG = 0.05


def _observed_at(acquire_time: str) -> str:
    """Render a scan's instant the way every other observation is stored.

    Two things depend on this and neither is obvious. `observation.date` is
    `substr(observed_at, 1, 10)` and is the app's universal join key, so a
    format that shifts the day files a scan under the wrong date. And
    idempotency ultimately rests on UNIQUE(observed_at, source), so the format
    must be deterministic across runs, not incidental.

    BodySpec documents `acquire_time` as being "in location timezone".
    `parse_iso_timestamp` does exactly the right thing with that: an offset is
    converted to Pacific, and a naive timestamp is taken as already local.
    (A scan taken outside Pacific and reported naive would be filed at its own
    wall-clock time, which keeps the calendar date right - the part that
    matters - even though the hour is nominal.)
    """
    return parse_iso_timestamp(acquire_time).strftime("%Y-%m-%d %H:%M:%S.%f")


def _promote(scan: dict) -> list[tuple[str, float, str | None]]:
    """The curated scalars, as (metric name, value, unit).

    Thirteen out of well over a hundred. Promoting the rest would make `metric`
    unreadable and `metric_def` a maintenance burden, for regional data that is
    browsed rather than trended - and nothing is lost, because the full payload
    is in `document.raw` and a scalar can be promoted later by re-running this
    over stored documents.
    """
    composition = scan.get("composition") or {}
    total = composition.get("total") or {}
    scan_info = scan.get("scan_info") or {}
    intake = scan_info.get("patient_intake") or {}
    visceral = scan.get("visceral_fat") or {}
    bone = (scan.get("bone_density") or {}).get("total") or {}
    percentile_metrics = (scan.get("percentiles") or {}).get("metrics") or {}

    total_mass_kg = total.get("total_mass_kg")
    fat_mass_kg = total.get("fat_mass_kg")
    lean_mass_kg = total.get("lean_mass_kg")
    bone_mass_kg = total.get("bone_mass_kg")

    if total_mass_kg is None or fat_mass_kg is None:
        raise ValueError(
            "composition.total is missing total_mass_kg or fat_mass_kg; "
            "without both there is no body weight and no fat-free mass, and "
            "a partial promotion would look like a complete one."
        )

    # The decomposition is what makes fat-free mass unambiguous. If it does not
    # hold, the payload is not the shape this promotion assumes and `ffm_kg` -
    # which feeds a daily calorie target - would be quietly wrong.
    if lean_mass_kg is not None and bone_mass_kg is not None:
        parts = fat_mass_kg + lean_mass_kg + bone_mass_kg
        if abs(parts - total_mass_kg) > DECOMPOSITION_TOLERANCE_KG:
            raise ValueError(
                f"fat {fat_mass_kg} + lean {lean_mass_kg} + bone "
                f"{bone_mass_kg} = {parts}, but total_mass_kg is "
                f"{total_mass_kg}. The composition payload is not the shape "
                f"this import assumes; ffm_kg and the RMR derived from it "
                f"would be wrong."
            )

    # LBM here is FAT-FREE mass, which INCLUDES bone - not `lean_mass_kg`,
    # which is lean soft tissue only. Using the latter understates LBM by
    # roughly 2.5-4 kg and RMR by 55-85 kcal/day: small enough to look
    # plausible, large enough to matter as a daily target. Confirmed from
    # BodySpec's own arithmetic - solving their published Cunningham figure
    # gives 73.2 kg, which is total - fat (73.16), not lean_mass_kg (69.61).
    ffm_kg = total_mass_kg - fat_mass_kg

    promoted: list[tuple[str, float, str | None]] = [
        # The only conversion. Body weight is the one quantity a DEXA scan
        # shares with the scale, so it has to share the scale's unit
        # (ADR-0003). `patient_intake.weight_kg` is deliberately NOT promoted:
        # it is the clipboard figure, 1.47 kg off the measured mass on the
        # 2026-03-10 scan, and promoting both would put two conflicting body
        # weight series in the database from one scan.
        ("body_weight_lb", total_mass_kg * KG_TO_LB, "lb"),
        ("fat_mass_kg", fat_mass_kg, "kg"),
        ("ffm_kg", ffm_kg, "kg"),
        (
            "rmr_kcal_per_day",
            RMR_INTERCEPT + RMR_PER_KG_FFM * ffm_kg,
            "kcal/day",
        ),
    ]

    def add(name: str, value, unit: str | None) -> None:
        if value is not None:
            promoted.append((name, float(value), unit))

    add("lean_mass_kg", lean_mass_kg, "kg")
    add("bone_mass_kg", bone_mass_kg, "kg")
    # tissue_fat_pct excludes bone and is the canonical body fat source, NOT
    # region_fat_pct. A deliberate divergence from BodySpec's own percentile
    # framing, which uses the region figure (~0.7pp lower). Never switch: the
    # two differ by about a percentage point, so changing mid-history
    # manufactures a step that reads as a real composition shift.
    add("body_fat_pct", total.get("tissue_fat_pct"), "%")
    add("android_gynoid_ratio", composition.get("android_gynoid_ratio"), None)
    add("vat_mass_kg", visceral.get("vat_mass_kg"), "kg")
    add(
        "bone_mineral_density_g_cm2",
        bone.get("bone_mineral_density"),
        "g/cm2",
    )
    add("height_cm", intake.get("height_cm"), "cm")

    # Values, never percentiles. A percentile is a function of the value and a
    # reference cohort that shifts as you age out of a band, so a stored one
    # silently changes meaning; the percentiles stay in document.raw, frozen
    # alongside the params that produced them.
    for name in ("total_lmi_kg_m2", "limb_lmi_kg_m2"):
        add(name, (percentile_metrics.get(name) or {}).get("value"), "kg/m2")

    return promoted


def _already_imported(session: Session, result_id: str) -> bool:
    return (
        session.execute(
            select(Document.id).where(
                Document.kind == DOCUMENT_KIND,
                Document.external_id == result_id,
            )
        ).first()
        is not None
    )


def _import_scan(session: Session, result_id: str, scan: dict, created_at) -> int:
    """Store one scan and promote it. Returns the number of metrics written."""
    acquire_time = (scan.get("scan_info") or {}).get("acquire_time")
    if not acquire_time:
        raise ValueError(
            f"scan {result_id} has no scan_info.acquire_time; there is no "
            f"instant to record it against."
        )

    document = Document(
        kind=DOCUMENT_KIND,
        source=SOURCE,
        external_id=result_id,
        raw=json.dumps(scan),
    )
    session.add(document)
    session.flush()

    observed_at = _observed_at(acquire_time)
    # UNIQUE(observed_at, source) means re-running against a scan whose
    # document was somehow removed reuses the observation rather than
    # colliding. Metrics are unique per (observation_id, name), so this is also
    # what lets a re-promotion be additive.
    observation = session.execute(
        select(Observation).where(
            Observation.observed_at == observed_at,
            Observation.source == SOURCE,
        )
    ).scalar_one_or_none()
    if observation is None:
        observation = Observation(
            observed_at=observed_at, source=SOURCE, created_at=created_at
        )
        session.add(observation)
        session.flush()

    existing = {
        name
        for name in session.execute(
            select(Metric.name).where(Metric.observation_id == observation.id)
        ).scalars()
    }

    written = 0
    for name, value, unit in _promote(scan):
        if name in existing:
            continue
        session.add(
            Metric(
                observation_id=observation.id,
                name=name,
                value=value,
                unit=unit,
                document_id=document.id,
            )
        )
        written += 1
    return written


def sync(client: BodySpecClient, token: str, session_factory, created_at) -> dict:
    """Import every scan not already held. Returns counts for the response.

    One transaction per scan rather than one for the whole sync, so a token
    that expires halfway leaves completed scans imported and re-running picks
    up the rest. That resumability is what makes a 60-minute credential safe
    here.
    """
    results = client.list_results(token)

    imported = 0
    skipped = 0
    metrics_written = 0

    for summary in results:
        result_id = summary.get("result_id")
        if not result_id:
            continue

        with session_factory() as session:
            if _already_imported(session, result_id):
                skipped += 1
                continue

        scan = client.fetch_scan(token, result_id)

        with session_factory() as session:
            # Re-checked inside the writing transaction: the read above was in
            # its own, and the unique index is the real guarantee anyway.
            if _already_imported(session, result_id):
                skipped += 1
                continue
            metrics_written += _import_scan(session, result_id, scan, created_at)
            session.commit()
            imported += 1
            logger.info("Imported BodySpec scan %s", result_id)

    return {
        "scans_found": len(results),
        "imported": imported,
        "skipped": skipped,
        "metrics_written": metrics_written,
    }
