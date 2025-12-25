"""Date and time utility functions."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

PACIFIC_TZ = ZoneInfo("America/Los_Angeles")


def get_current_datetime() -> datetime:
    """Get current datetime in Pacific timezone."""
    return datetime.now(PACIFIC_TZ)


def get_current_date() -> str:
    """Get current date in YYYY-MM-DD format (Pacific timezone)."""
    return get_current_datetime().date().isoformat()


def parse_iso_timestamp(timestamp_str: str) -> datetime:
    """Parse ISO 8601 timestamp string to datetime in Pacific timezone."""
    dt = datetime.fromisoformat(timestamp_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=PACIFIC_TZ)
    else:
        dt = dt.astimezone(PACIFIC_TZ)
    return dt


def format_timestamp(dt: datetime) -> str:
    """Format datetime to ISO 8601 string."""
    return dt.isoformat()


def project_future_dates(start_date: str, num_sessions: int, days_between: int = 2) -> list[str]:
    """
    Project future dates for upcoming workout sessions.

    Args:
        start_date: Starting date in YYYY-MM-DD format
        num_sessions: Number of sessions to project
        days_between: Days between each session

    Returns:
        List of dates in YYYY-MM-DD format
    """
    current_date = datetime.fromisoformat(start_date).date()
    dates = []

    for _ in range(num_sessions):
        current_date += timedelta(days=days_between)
        dates.append(current_date.isoformat())

    return dates
