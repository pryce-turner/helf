import pytest

from app.services.wendler_service import WendlerService

pytestmark = pytest.mark.usefixtures("db_engine")


def test_wendler_get_current_maxes_returns_dict():
    """Test that get_current_maxes returns a dict (may be empty if no workout data)."""
    service = WendlerService()
    maxes = service.get_current_maxes()

    assert isinstance(maxes, dict)
    # Keys should only be main lifts if present
    for key in maxes.keys():
        assert key in WendlerService.MAIN_LIFTS


def test_wendler_get_latest_estimated_1rm_returns_none_for_unknown():
    """Test that get_latest_estimated_1rm returns None for exercises with no data."""
    service = WendlerService()
    result = service.get_latest_estimated_1rm("Unknown Exercise That Does Not Exist")

    assert result is None
