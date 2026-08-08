"""add document and seed dexa metric defs

Revision ID: 61ccf127e583
Revises: e96bd4b90873
Create Date: 2026-08-08 14:02:11.903774

Two things a BodySpec import cannot work without.

`document` holds the raw scan payload. A single DEXA scan flattens to well over
a hundred scalars and only thirteen are worth promoting
(docs/plans/0008-bodyspec-integration.md §5), so the rest have to live
somewhere queryable or they are simply discarded. It also carries the
idempotency key: `external_id` is BodySpec's `result_id`, and the unique index
on (kind, external_id) is what makes a re-poll a no-op rather than a duplicate
history.

`metric.name` is a foreign key to `metric_def.name`, which means an unseeded
name is a failed INSERT, not a warning. Eleven of the thirteen promoted names
do not exist yet, so the import cannot write a single row until they are
defined here.

Plan 0005 specified `document` first; it has not landed, and Plan 0008 depends
on the table, so it is created here to that spec (with `external_id` present
from the start rather than bolted on by a later ALTER).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '61ccf127e583'
down_revision: str | Sequence[str] | None = 'e96bd4b90873'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (name, canonical_unit, description)
#
# Units are in the NAME, per ADR-0003 point 4, so a reader never has to consult
# a schema. Only `body_weight_lb` converts: it is the same quantity openScale
# measures and has to share an axis with it. Everything else here is a
# different quantity that never enters body-mass arithmetic, so it keeps
# BodySpec's source unit - which is ADR-0003's scope limit, not an exception to
# it.
DEXA_METRIC_DEFS = [
    (
        "fat_mass_kg",
        "kg",
        "Fat mass from DEXA. Source unit (kg) retained per ADR-0003's scope "
        "limit: a different quantity from body weight, never summed with it.",
    ),
    (
        "lean_mass_kg",
        "kg",
        "Lean SOFT TISSUE mass from DEXA - excludes bone. NOT fat-free mass; "
        "see ffm_kg. Also not comparable with openScale muscle_pct, which is a "
        "percentage of a different model entirely.",
    ),
    (
        "bone_mass_kg",
        "kg",
        "Bone mineral content expressed as mass, from DEXA. "
        "fat_mass_kg + lean_mass_kg + bone_mass_kg = total body mass.",
    ),
    (
        "ffm_kg",
        "kg",
        "Fat-free mass from DEXA: total_mass_kg - fat_mass_kg. INCLUDES bone; "
        "not the same as lean_mass_kg, which is lean soft tissue only. Stored "
        "rather than derived on read because it is the input to "
        "rmr_kcal_per_day and the derivation should be checkable.",
    ),
    (
        "vat_mass_kg",
        "kg",
        "Visceral adipose tissue mass from DEXA. Unrelated to openScale's "
        "unitless 'visceral fat' index.",
    ),
    (
        "bone_mineral_density_g_cm2",
        "g/cm2",
        "Whole-body bone mineral density from DEXA.",
    ),
    (
        "android_gynoid_ratio",
        None,
        "Ratio of android to gynoid fat from DEXA. Unitless by construction.",
    ),
    (
        "total_lmi_kg_m2",
        "kg/m2",
        "Total lean mass index from DEXA. The VALUE, not BodySpec's "
        "percentile: a percentile is a function of the value and a reference "
        "cohort that shifts as you age out of a band, so a stored one silently "
        "changes meaning. Percentiles stay in document.raw, frozen with the "
        "params that produced them.",
    ),
    (
        "limb_lmi_kg_m2",
        "kg/m2",
        "Appendicular lean mass index from DEXA. The value, not the "
        "percentile - see total_lmi_kg_m2.",
    ),
    (
        "height_cm",
        "cm",
        "Height as recorded at scan intake. Not a mass; ADR-0003 does not "
        "apply.",
    ),
    (
        "rmr_kcal_per_day",
        "kcal/day",
        "Resting metabolic rate, Katch-McArdle: 370 + 21.6 * FFM_kg, where FFM "
        "is ffm_kg (includes bone). Computed locally - BodySpec does not offer "
        "this formula; its own estimates (Cunningham et al.) stay in "
        "document.raw and run ~150 kcal/day higher. Do not mix formulas. "
        "Recorded against the scan's own observation, not a separate "
        "'derived' one: it is a number computed from an act of measuring, not "
        "a second act of measuring.",
    ),
]

# Already seeded by Plan 0003 (de63ed0bc62d). DEXA gives it a second source of
# very different accuracy, which the description now has to warn about - an
# INSERT here would be a primary-key conflict.
BODY_FAT_PCT_DESCRIPTION = (
    "Body fat percentage. DEXA source = BodySpec tissue_fat_pct (soft tissue, "
    "excludes bone) - NOT region_fat_pct, which BodySpec itself uses for "
    "percentile context and which runs ~0.7pp lower. Scale source = openScale "
    "bioimpedance. Distinguish by observation.source; never mix them in one "
    "series."
)

# Restored verbatim on downgrade so the round trip is lossless.
BODY_FAT_PCT_DESCRIPTION_BEFORE = "Body fat as a percentage of total mass."


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # --- guard the premise -------------------------------------------------
    #
    # Every check below can fail. If `document` already exists it was created
    # by something this migration does not know about, and creating it to a
    # different spec - or worse, adopting it - loses whatever it holds.
    if "document" in inspector.get_table_names():
        raise RuntimeError(
            "`document` already exists. This migration creates it to Plan "
            "0005's spec; if some other revision or a manual step created it, "
            "reconcile the two definitions by hand before continuing."
        )

    if "document_id" in {c["name"] for c in inspector.get_columns("metric")}:
        raise RuntimeError(
            "`metric.document_id` already exists. Adding it again would fail, "
            "and its presence means provenance is already wired up somewhere "
            "this migration does not account for."
        )

    # A name already in metric_def may carry a different unit or description,
    # and blindly overwriting it would silently redefine a quantity that
    # existing rows were recorded under.
    existing = set(
        conn.execute(sa.text("SELECT name FROM metric_def")).scalars().all()
    )
    collisions = sorted(
        name for name, _unit, _desc in DEXA_METRIC_DEFS if name in existing
    )
    if collisions:
        raise RuntimeError(
            f"metric_def already defines {collisions!r}. These are meant to be "
            f"new definitions; an existing row may use a different unit, and "
            f"overwriting it would redefine the quantity underneath rows "
            f"already recorded against it. Reconcile by hand."
        )

    # The UPDATE below is silent if the row is missing, which would leave the
    # dual-source warning unwritten with nothing to indicate it.
    if "body_fat_pct" not in existing:
        raise RuntimeError(
            "metric_def has no `body_fat_pct` row to update. Plan 0003's seed "
            "(de63ed0bc62d) should have created it; its absence means the "
            "vocabulary is not in the state this migration expects."
        )

    # --- document ----------------------------------------------------------
    op.create_table(
        "document",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "imported_at",
            sa.Text(),
            server_default=sa.text("(datetime('now'))"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        # BodySpec's `result_id`. NULL for documents with no upstream identity
        # (Plan 0005's notes and food imports), and SQLite treats NULLs as
        # distinct in a UNIQUE index, so those coexist freely while a
        # `result_id` can appear at most once per kind.
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("raw", sa.Text(), nullable=False),
        sa.CheckConstraint("json_valid(raw)", name="ck_document_raw_is_json"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_document_kind_external",
        "document",
        ["kind", "external_id"],
        unique=True,
    )

    # --- metric.document_id ------------------------------------------------
    #
    # Raw DDL, deliberately, and neither op.add_column nor batch_alter_table.
    #
    # `metric` carries a CHECK constraint, two foreign keys (one ON DELETE
    # CASCADE), a unique constraint and two indexes - every one of which a
    # batch rebuild is an opportunity to silently drop. SQLite accepts a
    # REFERENCES clause inline on ADD COLUMN when the default is NULL, so the
    # table is not rebuilt at all.
    #
    # op.add_column() cannot express this: it emits the column and then a
    # separate ALTER to add the constraint, which SQLite has no support for.
    op.execute("ALTER TABLE metric ADD COLUMN document_id INTEGER REFERENCES document(id)")

    # --- vocabulary --------------------------------------------------------
    for name, unit, description in DEXA_METRIC_DEFS:
        conn.execute(
            sa.text(
                "INSERT INTO metric_def (name, canonical_unit, description) "
                "VALUES (:name, :unit, :description)"
            ),
            {"name": name, "unit": unit, "description": description},
        )

    conn.execute(
        sa.text("UPDATE metric_def SET description = :d WHERE name = 'body_fat_pct'"),
        {"d": BODY_FAT_PCT_DESCRIPTION},
    )


def downgrade() -> None:
    conn = op.get_bind()

    # Dropping `document` discards raw payloads that cannot be reconstructed
    # from the promoted metrics - promotion is lossy by design, thirteen
    # scalars out of a hundred-odd. If anything has been imported, say so and
    # stop rather than deleting the only copy.
    linked = conn.execute(
        sa.text("SELECT count(*) FROM metric WHERE document_id IS NOT NULL")
    ).scalar_one()
    documents = conn.execute(sa.text("SELECT count(*) FROM document")).scalar_one()
    if linked or documents:
        raise RuntimeError(
            f"{documents} document(s) and {linked} metric(s) referencing them "
            f"would be destroyed. Raw payloads cannot be rebuilt from promoted "
            f"metrics. Roll the import back first (plan 0008 §10): "
            f"DELETE FROM observation WHERE source = 'bodyspec'; "
            f"DELETE FROM document WHERE kind = 'dexa_bodyspec';"
        )

    # Same argument one level down: a definition with rows behind it is in use,
    # and the FK would reject the delete anyway - better to name the offenders
    # than to surface an IntegrityError.
    in_use = sorted(
        conn.execute(
            sa.text(
                "SELECT DISTINCT name FROM metric WHERE name IN :names"
            ).bindparams(
                sa.bindparam(
                    "names",
                    value=[name for name, _u, _d in DEXA_METRIC_DEFS],
                    expanding=True,
                )
            )
        )
        .scalars()
        .all()
    )
    if in_use:
        raise RuntimeError(
            f"metric rows still reference {in_use!r}; removing those "
            f"definitions would orphan them. Delete the observations that "
            f"carry them first."
        )

    conn.execute(
        sa.text("UPDATE metric_def SET description = :d WHERE name = 'body_fat_pct'"),
        {"d": BODY_FAT_PCT_DESCRIPTION_BEFORE},
    )
    conn.execute(
        sa.text("DELETE FROM metric_def WHERE name IN :names").bindparams(
            sa.bindparam(
                "names",
                value=[name for name, _u, _d in DEXA_METRIC_DEFS],
                expanding=True,
            )
        )
    )

    # Raw DDL for the same reason as the upgrade: alembic's drop_column falls
    # back to a batch rebuild on SQLite, and `metric` has more constraints to
    # lose than this column is worth. 3.35+ supports DROP COLUMN directly.
    op.execute("ALTER TABLE metric DROP COLUMN document_id")
    op.drop_index("ux_document_kind_external", table_name="document")
    op.drop_table("document")
