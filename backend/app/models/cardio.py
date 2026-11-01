"""The cardio unit vocabulary (plan 0017).

Mirrored by a CHECK on `exercises.cardio_unit` and `workouts.amount_unit`
(a5f701728b12): the agent writes raw SQL and never passes through Pydantic
(ADR-0002), so the constraint is the rule both writers obey and this is the
copy that gives the HTTP side a 422 instead of a 500. Adding a unit means
changing both, in a migration.
"""

from typing import Literal

CardioUnit = Literal["miles", "km", "meters", "floors", "steps", "kcal"]
