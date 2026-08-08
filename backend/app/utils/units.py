"""Canonical units for stored measurements.

Pounds are canonical for all mass (ADR-0003). Nothing is stored in any other
unit, so no row carries a unit label - the unit is a property of the schema, not
of the data. `CANONICAL_WEIGHT_UNIT` is what the API reports.
"""

CANONICAL_WEIGHT_UNIT = "lbs"

# 1 kg in pounds, exact to the definition of the international pound. Used on
# ingest: openScale reports kilograms and always will.
KG_TO_LB = 2.20462262184878
