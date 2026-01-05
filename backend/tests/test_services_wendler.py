import pytest

from app.services.wendler_service import WendlerService

pytestmark = pytest.mark.usefixtures("db_engine")


def test_wendler_calculate_weights_rounding_rules():
    service = WendlerService()
    weights = service.calculate_weights(200, 1)
    assert weights == [(125, 5), (145, 5), (165, "5+")]


def test_wendler_generate_progression_sessions_and_counts():
    service = WendlerService()
    workouts = service.generate_progression(
        num_cycles=1,
        squat_max=200,
        bench_max=150,
        deadlift_max=250,
    )

    sessions = {w.session for w in workouts}
    assert len(workouts) == 72
    assert sessions == set(range(1, 13))

    first_session = [w for w in workouts if w.session == 1]
    assert len(first_session) == 6
    assert first_session[0].exercise == "Barbell Squat"


def test_wendler_generate_and_save_persists_workouts():
    service = WendlerService()
    result = service.generate_and_save(
        num_cycles=1,
        squat_max=200,
        bench_max=150,
        deadlift_max=250,
    )

    assert result["success"] is True
    assert result["count"] == 72
    assert result["session_range"] == [1, 12]
