"""Tests for workout_data module."""
import pytest
import csv
from pathlib import Path
from datetime import date
import workout_data


@pytest.fixture
def temp_csv_files(tmp_path, monkeypatch):
    """Create temporary CSV files for testing."""
    # Set up temporary file paths
    workout_csv = tmp_path / "workouts.csv"
    upcoming_csv = tmp_path / "upcoming_workouts.csv"

    # Patch the module-level CSV file paths
    monkeypatch.setattr(workout_data, 'CSV_FILE', workout_csv)
    monkeypatch.setattr(workout_data, 'UPCOMING_CSV_FILE', upcoming_csv)

    return {'workouts': workout_csv, 'upcoming': upcoming_csv}


@pytest.fixture
def sample_workouts():
    """Sample workout data for testing."""
    return [
        {
            'Date': '2024-01-01',
            'Exercise': 'Barbell Squat',
            'Category': 'Legs',
            'Weight': '225',
            'Weight Unit': 'lbs',
            'Reps': '5',
            'Distance': '',
            'Distance Unit': '',
            'Time': '',
            'Comment': 'Good form'
        },
        {
            'Date': '2024-01-01',
            'Exercise': 'Bench Press',
            'Category': 'Chest',
            'Weight': '185',
            'Weight Unit': 'lbs',
            'Reps': '8',
            'Distance': '',
            'Distance Unit': '',
            'Time': '',
            'Comment': ''
        },
        {
            'Date': '2024-01-03',
            'Exercise': 'Barbell Squat',
            'Category': 'Legs',
            'Weight': '235',
            'Weight Unit': 'lbs',
            'Reps': '5',
            'Distance': '',
            'Distance Unit': '',
            'Time': '',
            'Comment': ''
        }
    ]


@pytest.fixture
def sample_upcoming():
    """Sample upcoming workout data for testing."""
    return [
        {
            'Session': '0',
            'Exercise': 'Deadlift',
            'Category': 'Back',
            'Weight': '315',
            'Weight Unit': 'lbs',
            'Reps': '5',
            'Distance': '',
            'Distance Unit': '',
            'Time': '',
            'Comment': ''
        },
        {
            'Session': '0',
            'Exercise': 'Pull-ups',
            'Category': 'Back',
            'Weight': '0',
            'Weight Unit': 'lbs',
            'Reps': '10',
            'Distance': '',
            'Distance Unit': '',
            'Time': '',
            'Comment': 'Bodyweight'
        },
        {
            'Session': '1',
            'Exercise': 'Bench Press',
            'Category': 'Chest',
            'Weight': '225',
            'Weight Unit': 'lbs',
            'Reps': '3',
            'Distance': '',
            'Distance Unit': '',
            'Time': '',
            'Comment': ''
        }
    ]


class TestReadWriteWorkouts:
    """Test basic read/write operations."""

    def test_read_workouts_empty(self, temp_csv_files):
        """Test reading from non-existent file returns empty list."""
        result = workout_data.read_workouts()
        assert result == []

    def test_write_workout(self, temp_csv_files, sample_workouts):
        """Test writing a single workout."""
        workout_data.write_workout(sample_workouts[0])

        # Verify file was created
        assert temp_csv_files['workouts'].exists()

        # Read back and verify
        workouts = workout_data.read_workouts()
        assert len(workouts) == 1
        assert workouts[0]['Exercise'] == 'Barbell Squat'
        assert workouts[0]['Weight'] == '225'

    def test_write_multiple_workouts(self, temp_csv_files, sample_workouts):
        """Test writing multiple workouts."""
        for workout in sample_workouts:
            workout_data.write_workout(workout)

        workouts = workout_data.read_workouts()
        assert len(workouts) == 3
        assert workouts[0]['Exercise'] == 'Barbell Squat'
        assert workouts[2]['Date'] == '2024-01-03'

    def test_read_workouts_by_date(self, temp_csv_files, sample_workouts):
        """Test filtering workouts by date."""
        for workout in sample_workouts:
            workout_data.write_workout(workout)

        # Get workouts for 2024-01-01
        jan1_workouts = workout_data.read_workouts_by_date('2024-01-01')
        assert len(jan1_workouts) == 2
        assert all(w['Date'] == '2024-01-01' for w in jan1_workouts)

        # Get workouts for 2024-01-03
        jan3_workouts = workout_data.read_workouts_by_date('2024-01-03')
        assert len(jan3_workouts) == 1
        assert jan3_workouts[0]['Exercise'] == 'Barbell Squat'

        # Non-existent date
        empty = workout_data.read_workouts_by_date('2024-01-05')
        assert empty == []


class TestUpdateDeleteWorkouts:
    """Test update and delete operations."""

    def test_update_workout(self, temp_csv_files, sample_workouts):
        """Test updating an existing workout."""
        # Write initial workouts
        for workout in sample_workouts:
            workout_data.write_workout(workout)

        # Update the first workout
        original = sample_workouts[0].copy()
        updated = sample_workouts[0].copy()
        updated['Weight'] = '245'
        updated['Comment'] = 'PR!'

        workout_data.update_workout(original, updated)

        # Verify update
        workouts = workout_data.read_workouts()
        assert len(workouts) == 3  # Same count

        # Find the updated workout
        found = False
        for w in workouts:
            if w['Exercise'] == 'Barbell Squat' and w['Date'] == '2024-01-01':
                assert w['Weight'] == '245'
                assert w['Comment'] == 'PR!'
                found = True
                break
        assert found, "Updated workout not found"

    def test_delete_workout(self, temp_csv_files, sample_workouts):
        """Test deleting a workout."""
        # Write initial workouts
        for workout in sample_workouts:
            workout_data.write_workout(workout)

        # Delete the second workout
        workout_data.delete_workout(sample_workouts[1])

        # Verify deletion
        workouts = workout_data.read_workouts()
        assert len(workouts) == 2

        # Verify the deleted workout is gone
        exercises = [w['Exercise'] for w in workouts]
        assert 'Bench Press' not in exercises
        assert 'Barbell Squat' in exercises


class TestWorkoutQueries:
    """Test query functions."""

    def test_get_workout_dates(self, temp_csv_files, sample_workouts):
        """Test getting all unique workout dates."""
        for workout in sample_workouts:
            workout_data.write_workout(workout)

        dates = workout_data.get_workout_dates()
        assert dates == ['2024-01-01', '2024-01-03']

    def test_get_workout_count_by_date(self, temp_csv_files, sample_workouts):
        """Test counting workouts per date."""
        for workout in sample_workouts:
            workout_data.write_workout(workout)

        counts = workout_data.get_workout_count_by_date()
        assert counts['2024-01-01'] == 2
        assert counts['2024-01-03'] == 1

    def test_get_categories(self, temp_csv_files, sample_workouts):
        """Test getting all unique categories."""
        for workout in sample_workouts:
            workout_data.write_workout(workout)

        categories = workout_data.get_categories()
        assert 'Legs' in categories
        assert 'Chest' in categories
        assert len(categories) == 2

    def test_get_exercises_by_category(self, temp_csv_files, sample_workouts):
        """Test getting exercises grouped by category."""
        for workout in sample_workouts:
            workout_data.write_workout(workout)

        exercises = workout_data.get_exercises_by_category()

        assert 'Legs' in exercises
        assert 'Barbell Squat' in exercises['Legs']
        assert 'Chest' in exercises
        assert 'Bench Press' in exercises['Chest']

    def test_get_exercises_sorted_by_date(self, temp_csv_files):
        """Test that exercises are sorted by most recent date."""
        # Create workouts with different dates
        workouts = [
            {
                'Date': '2024-01-01',
                'Exercise': 'Exercise A',
                'Category': 'Cat1',
                'Weight': '100',
                'Weight Unit': 'lbs',
                'Reps': '10',
                'Distance': '',
                'Distance Unit': '',
                'Time': '',
                'Comment': ''
            },
            {
                'Date': '2024-01-05',
                'Exercise': 'Exercise B',
                'Category': 'Cat1',
                'Weight': '100',
                'Weight Unit': 'lbs',
                'Reps': '10',
                'Distance': '',
                'Distance Unit': '',
                'Time': '',
                'Comment': ''
            },
            {
                'Date': '2024-01-03',
                'Exercise': 'Exercise C',
                'Category': 'Cat1',
                'Weight': '100',
                'Weight Unit': 'lbs',
                'Reps': '10',
                'Distance': '',
                'Distance Unit': '',
                'Time': '',
                'Comment': ''
            }
        ]

        for workout in workouts:
            workout_data.write_workout(workout)

        exercises = workout_data.get_exercises_by_category()

        # Should be sorted by most recent date (descending)
        assert exercises['Cat1'][0] == 'Exercise B'  # 2024-01-05
        assert exercises['Cat1'][1] == 'Exercise C'  # 2024-01-03
        assert exercises['Cat1'][2] == 'Exercise A'  # 2024-01-01


class TestUpcomingWorkouts:
    """Test upcoming workout functions."""

    def test_read_upcoming_workouts_empty(self, temp_csv_files):
        """Test reading from non-existent upcoming file."""
        result = workout_data.read_upcoming_workouts()
        assert result == []

    def test_read_upcoming_workouts(self, temp_csv_files, sample_upcoming):
        """Test reading upcoming workouts."""
        # Write sample data
        with open(temp_csv_files['upcoming'], 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=workout_data.UPCOMING_CSV_HEADERS)
            writer.writeheader()
            writer.writerows(sample_upcoming)

        workouts = workout_data.read_upcoming_workouts()
        assert len(workouts) == 3
        assert workouts[0]['Exercise'] == 'Deadlift'

    def test_get_lowest_session_index(self, temp_csv_files, sample_upcoming):
        """Test getting the lowest session index."""
        # Write sample data
        with open(temp_csv_files['upcoming'], 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=workout_data.UPCOMING_CSV_HEADERS)
            writer.writeheader()
            writer.writerows(sample_upcoming)

        lowest = workout_data.get_lowest_session_index()
        assert lowest == 0

    def test_get_lowest_session_index_empty(self, temp_csv_files):
        """Test getting lowest session when no data exists."""
        lowest = workout_data.get_lowest_session_index()
        assert lowest is None

    def test_pop_upcoming_workout_session(self, temp_csv_files, sample_upcoming):
        """Test popping a session from upcoming workouts."""
        # Write sample data
        with open(temp_csv_files['upcoming'], 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=workout_data.UPCOMING_CSV_HEADERS)
            writer.writeheader()
            writer.writerows(sample_upcoming)

        # Pop session 0
        count = workout_data.pop_upcoming_workout_session('2024-01-10')
        assert count == 2  # Two exercises in session 0

        # Verify historical workouts were created
        historical = workout_data.read_workouts_by_date('2024-01-10')
        assert len(historical) == 2
        assert any(w['Exercise'] == 'Deadlift' for w in historical)
        assert any(w['Exercise'] == 'Pull-ups' for w in historical)

        # Verify session 0 was removed from upcoming
        remaining = workout_data.read_upcoming_workouts()
        assert len(remaining) == 1
        assert remaining[0]['Session'] == '1'

    def test_pop_upcoming_workout_session_empty(self, temp_csv_files):
        """Test popping when no upcoming workouts exist."""
        count = workout_data.pop_upcoming_workout_session('2024-01-10')
        assert count == 0


class TestEstimated1RM:
    """Test estimated 1RM calculations."""

    def test_calculate_estimated_1rm_basic(self):
        """Test basic 1RM calculation."""
        # Using formula: (0.033 × reps × weight) + weight
        result = workout_data.calculate_estimated_1rm(225, 5)
        expected = (0.033 * 5 * 225) + 225
        assert abs(result - expected) < 0.01

    def test_calculate_estimated_1rm_one_rep(self):
        """Test 1RM calculation with 1 rep."""
        result = workout_data.calculate_estimated_1rm(315, 1)
        expected = (0.033 * 1 * 315) + 315
        assert abs(result - expected) < 0.01

    def test_calculate_estimated_1rm_string_inputs(self):
        """Test 1RM calculation with string inputs."""
        result = workout_data.calculate_estimated_1rm('225', '5')
        assert result > 0

    def test_calculate_estimated_1rm_invalid_inputs(self):
        """Test 1RM calculation with invalid inputs."""
        result = workout_data.calculate_estimated_1rm('', '')
        assert result == 0

        result = workout_data.calculate_estimated_1rm('abc', '5')
        assert result == 0

        result = workout_data.calculate_estimated_1rm('225', 'abc')
        assert result == 0

    def test_calculate_estimated_1rm_zero_reps(self):
        """Test 1RM calculation with zero reps."""
        result = workout_data.calculate_estimated_1rm(225, 0)
        # With 0 reps, formula gives: (0.033 * 0 * 225) + 225 = 225
        assert result == 225.0


class TestProgressionData:
    """Test progression data aggregation."""

    def test_get_progression_data_historical_only(self, temp_csv_files):
        """Test progression data with only historical workouts."""
        workouts = [
            {
                'Date': '2024-01-01',
                'Exercise': 'Barbell Squat',
                'Category': 'Legs',
                'Weight': '225',
                'Weight Unit': 'lbs',
                'Reps': '5',
                'Distance': '',
                'Distance Unit': '',
                'Time': '',
                'Comment': ''
            },
            {
                'Date': '2024-01-03',
                'Exercise': 'Barbell Squat',
                'Category': 'Legs',
                'Weight': '235',
                'Weight Unit': 'lbs',
                'Reps': '5',
                'Distance': '',
                'Distance Unit': '',
                'Time': '',
                'Comment': ''
            }
        ]

        for workout in workouts:
            workout_data.write_workout(workout)

        data = workout_data.get_progression_data('Barbell Squat')

        assert len(data['historical']) == 2
        assert len(data['upcoming']) == 0
        assert data['historical'][0]['Date'] == '2024-01-01'
        assert data['historical'][1]['Date'] == '2024-01-03'
        assert 'estimated_1rm' in data['historical'][0]

    def test_get_progression_data_best_set_per_day(self, temp_csv_files):
        """Test that only best set per day is returned."""
        workouts = [
            {
                'Date': '2024-01-01',
                'Exercise': 'Bench Press',
                'Category': 'Chest',
                'Weight': '185',
                'Weight Unit': 'lbs',
                'Reps': '10',
                'Distance': '',
                'Distance Unit': '',
                'Time': '',
                'Comment': 'Warm up'
            },
            {
                'Date': '2024-01-01',
                'Exercise': 'Bench Press',
                'Category': 'Chest',
                'Weight': '225',
                'Weight Unit': 'lbs',
                'Reps': '5',
                'Distance': '',
                'Distance Unit': '',
                'Time': '',
                'Comment': 'Heavy set'
            },
            {
                'Date': '2024-01-01',
                'Exercise': 'Bench Press',
                'Category': 'Chest',
                'Weight': '205',
                'Weight Unit': 'lbs',
                'Reps': '8',
                'Distance': '',
                'Distance Unit': '',
                'Time': '',
                'Comment': 'Burnout'
            }
        ]

        for workout in workouts:
            workout_data.write_workout(workout)

        data = workout_data.get_progression_data('Bench Press')

        # Should only return 1 workout (best set for the day)
        assert len(data['historical']) == 1

        # Should be the set with highest estimated 1RM
        best = data['historical'][0]
        assert best['Weight'] == '225'
        assert best['Reps'] == '5'

    def test_get_progression_data_no_data(self, temp_csv_files):
        """Test progression data when exercise doesn't exist."""
        data = workout_data.get_progression_data('Nonexistent Exercise')

        assert data['historical'] == []
        assert data['upcoming'] == []


class TestMainLifts:
    """Test main lifts function."""

    def test_get_main_lifts_empty(self, temp_csv_files):
        """Test getting main lifts when no data exists."""
        lifts = workout_data.get_main_lifts()
        assert lifts == []

    def test_get_main_lifts_from_historical(self, temp_csv_files, sample_workouts):
        """Test getting main lifts from historical workouts."""
        for workout in sample_workouts:
            workout_data.write_workout(workout)

        lifts = workout_data.get_main_lifts()

        assert 'Barbell Squat' in lifts
        assert 'Bench Press' in lifts
        assert len(lifts) == 2

    def test_get_main_lifts_from_upcoming(self, temp_csv_files, sample_upcoming):
        """Test getting main lifts from upcoming workouts."""
        with open(temp_csv_files['upcoming'], 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=workout_data.UPCOMING_CSV_HEADERS)
            writer.writeheader()
            writer.writerows(sample_upcoming)

        lifts = workout_data.get_main_lifts()

        assert 'Deadlift' in lifts
        assert 'Pull-ups' in lifts
        assert 'Bench Press' in lifts

    def test_get_main_lifts_combined(self, temp_csv_files, sample_workouts, sample_upcoming):
        """Test getting main lifts from both historical and upcoming."""
        for workout in sample_workouts:
            workout_data.write_workout(workout)

        with open(temp_csv_files['upcoming'], 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=workout_data.UPCOMING_CSV_HEADERS)
            writer.writeheader()
            writer.writerows(sample_upcoming)

        lifts = workout_data.get_main_lifts()

        # Should have exercises from both sources
        assert 'Barbell Squat' in lifts  # From historical
        assert 'Deadlift' in lifts  # From upcoming
        assert 'Pull-ups' in lifts  # From upcoming
        assert 'Bench Press' in lifts  # From both

        # Check sorted
        assert lifts == sorted(lifts)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
