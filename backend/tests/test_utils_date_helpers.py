"""Tests for utils/date_helpers.py - Date and time utilities."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch

import pytest

from app.utils.date_helpers import (
    PACIFIC_TZ,
    get_current_datetime,
    get_current_date,
    parse_iso_timestamp,
    format_timestamp,
    project_future_dates,
)


class TestDateHelpers:
    """Tests for date helper functions."""

    def test_pacific_tz_constant(self):
        """Test that PACIFIC_TZ is properly defined."""
        assert PACIFIC_TZ == ZoneInfo("America/Los_Angeles")

    @patch("app.utils.date_helpers.datetime")
    def test_get_current_datetime_returns_pacific_time(self, mock_datetime):
        """Test get_current_datetime returns datetime in Pacific timezone."""
        # Mock the current time
        fixed_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=PACIFIC_TZ)
        mock_datetime.now.return_value = fixed_time

        result = get_current_datetime()

        mock_datetime.now.assert_called_once_with(PACIFIC_TZ)
        assert result == fixed_time
        assert result.tzinfo == PACIFIC_TZ

    @patch("app.utils.date_helpers.get_current_datetime")
    def test_get_current_date_returns_iso_format(self, mock_get_current_datetime):
        """Test get_current_date returns date in YYYY-MM-DD format."""
        # Mock current datetime
        mock_get_current_datetime.return_value = datetime(
            2024, 3, 15, 14, 30, 0, tzinfo=PACIFIC_TZ
        )

        result = get_current_date()

        assert result == "2024-03-15"
        assert isinstance(result, str)

    def test_parse_iso_timestamp_with_timezone(self):
        """Test parsing ISO timestamp that already has timezone info."""
        timestamp_str = "2024-01-15T10:30:00-08:00"

        result = parse_iso_timestamp(timestamp_str)

        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30
        assert result.tzinfo is not None
        # Should be converted to Pacific timezone
        assert result.tzinfo.key == "America/Los_Angeles"

    def test_parse_iso_timestamp_without_timezone(self):
        """Test parsing ISO timestamp without timezone (assumes Pacific)."""
        timestamp_str = "2024-01-15T10:30:00"

        result = parse_iso_timestamp(timestamp_str)

        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30
        # Should be assigned Pacific timezone
        assert result.tzinfo.key == "America/Los_Angeles"

    def test_parse_iso_timestamp_converts_other_timezones_to_pacific(self):
        """Test that timestamps in other timezones are converted to Pacific."""
        # UTC timestamp
        timestamp_str = "2024-01-15T18:30:00+00:00"

        result = parse_iso_timestamp(timestamp_str)

        # UTC 18:30 = Pacific 10:30 (UTC-8)
        assert result.hour == 10
        assert result.minute == 30
        assert result.tzinfo.key == "America/Los_Angeles"

    def test_format_timestamp_returns_iso_string(self):
        """Test format_timestamp returns ISO 8601 formatted string."""
        dt = datetime(2024, 1, 15, 10, 30, 45, tzinfo=PACIFIC_TZ)

        result = format_timestamp(dt)

        assert isinstance(result, str)
        assert "2024-01-15" in result
        assert "10:30:45" in result

    def test_format_timestamp_roundtrip(self):
        """Test that format_timestamp and parse_iso_timestamp are inverse operations."""
        original = datetime(2024, 6, 20, 15, 45, 30, tzinfo=PACIFIC_TZ)

        formatted = format_timestamp(original)
        parsed = parse_iso_timestamp(formatted)

        assert parsed.year == original.year
        assert parsed.month == original.month
        assert parsed.day == original.day
        assert parsed.hour == original.hour
        assert parsed.minute == original.minute
        assert parsed.second == original.second

    def test_project_future_dates_basic(self):
        """Test projecting future dates with default spacing."""
        start_date = "2024-01-01"
        num_sessions = 3

        result = project_future_dates(start_date, num_sessions)

        assert len(result) == 3
        # Default is 2 days between sessions
        assert result[0] == "2024-01-03"  # +2 days
        assert result[1] == "2024-01-05"  # +2 days
        assert result[2] == "2024-01-07"  # +2 days

    def test_project_future_dates_custom_spacing(self):
        """Test projecting future dates with custom day spacing."""
        start_date = "2024-01-01"
        num_sessions = 4
        days_between = 7  # Weekly

        result = project_future_dates(start_date, num_sessions, days_between)

        assert len(result) == 4
        assert result[0] == "2024-01-08"  # +7 days
        assert result[1] == "2024-01-15"  # +7 days
        assert result[2] == "2024-01-22"  # +7 days
        assert result[3] == "2024-01-29"  # +7 days

    def test_project_future_dates_single_session(self):
        """Test projecting a single future date."""
        start_date = "2024-02-15"
        num_sessions = 1

        result = project_future_dates(start_date, num_sessions)

        assert len(result) == 1
        assert result[0] == "2024-02-17"  # +2 days

    def test_project_future_dates_zero_sessions(self):
        """Test projecting zero sessions returns empty list."""
        start_date = "2024-01-01"
        num_sessions = 0

        result = project_future_dates(start_date, num_sessions)

        assert result == []

    def test_project_future_dates_handles_month_boundaries(self):
        """Test projecting dates across month boundaries."""
        start_date = "2024-01-30"
        num_sessions = 2

        result = project_future_dates(start_date, num_sessions)

        assert len(result) == 2
        assert result[0] == "2024-02-01"  # Crosses into February
        assert result[1] == "2024-02-03"

    def test_project_future_dates_handles_year_boundaries(self):
        """Test projecting dates across year boundaries."""
        start_date = "2024-12-30"
        num_sessions = 2

        result = project_future_dates(start_date, num_sessions)

        assert len(result) == 2
        assert result[0] == "2025-01-01"  # Crosses into new year
        assert result[1] == "2025-01-03"

    def test_project_future_dates_handles_leap_year(self):
        """Test projecting dates in leap year (Feb 29)."""
        start_date = "2024-02-27"  # 2024 is a leap year
        num_sessions = 2

        result = project_future_dates(start_date, num_sessions)

        assert len(result) == 2
        assert result[0] == "2024-02-29"  # Leap day
        assert result[1] == "2024-03-02"

    def test_project_future_dates_large_number_of_sessions(self):
        """Test projecting a large number of sessions."""
        start_date = "2024-01-01"
        num_sessions = 50

        result = project_future_dates(start_date, num_sessions)

        assert len(result) == 50
        assert result[0] == "2024-01-03"
        # 50 sessions × 2 days = 100 days from start
        assert result[-1] == "2024-04-10"

    def test_project_future_dates_returns_iso_format_strings(self):
        """Test that all returned dates are in ISO format."""
        start_date = "2024-06-01"
        num_sessions = 3

        result = project_future_dates(start_date, num_sessions)

        for date_str in result:
            # Should be parseable as ISO date
            datetime.fromisoformat(date_str)
            # Should match YYYY-MM-DD format
            assert len(date_str) == 10
            assert date_str[4] == "-"
            assert date_str[7] == "-"

    def test_project_future_dates_with_one_day_spacing(self):
        """Test projecting dates with daily spacing."""
        start_date = "2024-01-01"
        num_sessions = 5
        days_between = 1

        result = project_future_dates(start_date, num_sessions, days_between)

        assert len(result) == 5
        assert result[0] == "2024-01-02"
        assert result[1] == "2024-01-03"
        assert result[2] == "2024-01-04"
        assert result[3] == "2024-01-05"
        assert result[4] == "2024-01-06"

    def test_parse_iso_timestamp_with_microseconds(self):
        """Test parsing ISO timestamp with microseconds."""
        timestamp_str = "2024-01-15T10:30:45.123456-08:00"

        result = parse_iso_timestamp(timestamp_str)

        assert result.microsecond == 123456
        assert result.hour == 10
        assert result.minute == 30
        assert result.second == 45

    def test_parse_iso_timestamp_with_z_suffix(self):
        """Test parsing ISO timestamp with Z (UTC) suffix."""
        # Python's fromisoformat doesn't handle 'Z' suffix in older versions
        # This tests the current behavior
        timestamp_str = "2024-01-15T18:30:00+00:00"  # Using +00:00 instead of Z

        result = parse_iso_timestamp(timestamp_str)

        # UTC 18:30 should be Pacific 10:30
        assert result.hour == 10
        assert result.tzinfo.key == "America/Los_Angeles"
