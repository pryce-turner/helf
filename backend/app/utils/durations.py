"""Legacy duration parsing.

`workouts.time` (and `upcoming_workouts.time`) is a free-form legacy string —
`'0:30'`, `'0:00:45'`. Since plan 0018 the numeric `work_seconds` is the
writable field and the string is read-only, so the one place a legacy value
may still need translating is promotion: transferring a pending session onto
a day. Both transfer paths call `parse_duration_seconds`.

Bounded to the target column's CHECK (`ck_workouts_work_seconds`, 1..3600):
an out-of-range or unparseable value is None, never a constraint violation
waiting to happen. The migrations carry their own copies of this pattern on
purpose — a migration must run against the schema of its day, not today's.
"""

import re

#: h:mm:ss first — the two shapes share a suffix, so the longer pattern wins.
_H_MM_SS_RE = re.compile(r"^(\d{1,4}):([0-5]\d):([0-5]\d)$")
_M_SS_RE = re.compile(r"^(\d{1,4}):([0-5]\d)$")

MAX_SECONDS = 3600  # ck_workouts_work_seconds upper bound


def parse_duration_seconds(time_value: str | None) -> int | None:
    """Seconds from `h:mm:ss` or `m:ss`, or None when ambiguous or unbounded."""
    if not time_value:
        return None
    value = time_value.strip()
    match = _H_MM_SS_RE.match(value)
    if match:
        seconds = (
            int(match.group(1)) * 3600
            + int(match.group(2)) * 60
            + int(match.group(3))
        )
    else:
        match = _M_SS_RE.match(value)
        if not match:
            return None
        seconds = int(match.group(1)) * 60 + int(match.group(2))
    return seconds if 1 <= seconds <= MAX_SECONDS else None
