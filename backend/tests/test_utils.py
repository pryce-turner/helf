from datetime import datetime

from app.utils.calculations import calculate_estimated_1rm, calculate_moving_average
from app.utils.date_helpers import (
    format_timestamp,
    parse_iso_timestamp,
    project_future_dates,
    PACIFIC_TZ,
)


def test_calculate_estimated_1rm_handles_plus_string():
    assert calculate_estimated_1rm(100, "5+") == 116.5


def test_calculate_estimated_1rm_handles_invalid_values():
    assert calculate_estimated_1rm("bad", "x") == 0.0


def test_calculate_moving_average_skips_none_values():
    values = [1.0, None, 3.0, 5.0]
    assert calculate_moving_average(values, window=2) == [1.0, None, 3.0, 4.0]


def test_parse_iso_timestamp_assigns_timezone():
    dt = parse_iso_timestamp("2024-01-01T12:00:00")
    assert dt.tzinfo == PACIFIC_TZ


def test_parse_iso_timestamp_converts_timezone():
    dt = parse_iso_timestamp("2024-01-01T20:00:00+00:00")
    assert dt.tzinfo == PACIFIC_TZ


def test_format_timestamp_round_trip():
    dt = datetime(2024, 1, 2, 3, 4, 5, tzinfo=PACIFIC_TZ)
    assert format_timestamp(dt) == dt.isoformat()


def test_project_future_dates_steps_by_days():
    assert project_future_dates("2024-01-01", 3, days_between=2) == [
        "2024-01-03",
        "2024-01-05",
        "2024-01-07",
    ]
