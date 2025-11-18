"""Workout data management module."""
import csv
import os
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

# Pacific timezone
PACIFIC_TZ = ZoneInfo("America/Los_Angeles")

# CSV file paths - use DATA_DIR environment variable or current directory
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
CSV_FILE = DATA_DIR / "workouts.csv"
CSV_HEADERS = ["Date", "Exercise", "Category", "Weight", "Weight Unit", "Reps",
               "Distance", "Distance Unit", "Time", "Comment", "Order"]

UPCOMING_CSV_FILE = DATA_DIR / "upcoming_workouts.csv"
UPCOMING_CSV_HEADERS = ["Session", "Exercise", "Category", "Weight", "Weight Unit", "Reps",
                        "Distance", "Distance Unit", "Time", "Comment"]


def read_workouts():
    """Read all workouts from CSV file."""
    if not CSV_FILE.exists():
        return []

    workouts = []
    with open(CSV_FILE, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            workouts.append(row)
    return workouts


def read_workouts_by_date(target_date):
    """Read workouts for a specific date, sorted by order."""
    all_workouts = read_workouts()
    date_workouts = [w for w in all_workouts if w['Date'] == target_date]

    # Sort by order (handle missing order field)
    def get_order(workout):
        try:
            return int(workout.get('Order', 999))
        except (ValueError, TypeError):
            return 999

    date_workouts.sort(key=get_order)
    return date_workouts


def write_workout(workout_data):
    """Write a single workout to CSV file."""
    # If order not specified, assign next available order for the date
    if 'Order' not in workout_data or not workout_data['Order']:
        date = workout_data.get('Date', '')
        existing_workouts = read_workouts_by_date(date)
        if existing_workouts:
            max_order = max(int(w.get('Order', 0)) for w in existing_workouts if w.get('Order', '').isdigit())
            workout_data['Order'] = str(max_order + 1)
        else:
            workout_data['Order'] = '1'

    file_exists = CSV_FILE.exists()

    # Check if file exists and doesn't end with newline
    needs_newline = False
    if file_exists and CSV_FILE.stat().st_size > 0:
        with open(CSV_FILE, 'rb') as f:
            f.seek(-1, 2)  # Go to last byte
            needs_newline = f.read(1) != b'\n'

    with open(CSV_FILE, 'a', newline='') as f:
        # Add newline if the file doesn't end with one
        if needs_newline:
            f.write('\n')

        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)

        # Write header if file doesn't exist
        if not file_exists:
            writer.writeheader()

        writer.writerow(workout_data)


def get_workout_dates():
    """Get all unique dates that have workouts."""
    workouts = read_workouts()
    dates = set()
    for workout in workouts:
        if workout['Date']:
            dates.add(workout['Date'])
    return sorted(dates)


def get_workout_count_by_date():
    """Get a dictionary of date -> workout count."""
    workouts = read_workouts()
    counts = {}
    for workout in workouts:
        date = workout['Date']
        counts[date] = counts.get(date, 0) + 1
    return counts


def get_exercises_by_category():
    """Get all unique exercises grouped by category, sorted by most recently logged."""
    workouts = read_workouts()
    exercises_by_category = {}

    # Track the most recent date for each exercise in each category
    exercise_dates = {}

    for workout in workouts:
        category = workout.get('Category', 'Uncategorized')
        exercise = workout.get('Exercise', '')
        date = workout.get('Date', '')

        if category and exercise:
            if category not in exercises_by_category:
                exercises_by_category[category] = set()
                exercise_dates[category] = {}

            exercises_by_category[category].add(exercise)

            # Track the most recent date for this exercise
            if exercise not in exercise_dates[category] or date > exercise_dates[category][exercise]:
                exercise_dates[category][exercise] = date

    # Convert sets to lists sorted by most recent date (descending)
    result = {}
    for cat in sorted(exercises_by_category.keys()):
        exercises = list(exercises_by_category[cat])
        # Sort by date descending (most recent first)
        exercises.sort(key=lambda ex: exercise_dates[cat].get(ex, ''), reverse=True)
        result[cat] = exercises

    return result


def get_categories():
    """Get all unique categories."""
    exercises_by_category = get_exercises_by_category()
    return sorted(list(exercises_by_category.keys()))


def update_workout(original_workout, updated_workout):
    """Update a specific workout in the CSV file."""
    workouts = read_workouts()

    # Find and update the matching workout
    updated = False
    for i, workout in enumerate(workouts):
        if workout == original_workout:
            workouts[i] = updated_workout
            updated = True
            break

    if not updated:
        # If exact match not found, just append as new
        workouts.append(updated_workout)

    # Write all workouts back to file
    with open(CSV_FILE, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(workouts)


def delete_workout(workout_to_delete):
    """Delete a specific workout from the CSV file."""
    workouts = read_workouts()

    # Remove the matching workout
    workouts = [w for w in workouts if w != workout_to_delete]

    # Write all workouts back to file
    with open(CSV_FILE, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(workouts)


def reorder_workout(target_date, workout_index, direction):
    """
    Reorder a workout within a specific date by moving it up or down.

    Args:
        target_date: Date of the workouts to reorder
        workout_index: Index of the workout in the date's workout list
        direction: 'up' to move earlier, 'down' to move later

    Returns:
        True if successful, False if at boundary
    """
    # Get all workouts for this date
    date_workouts = read_workouts_by_date(target_date)

    if not date_workouts or workout_index < 0 or workout_index >= len(date_workouts):
        return False

    # Check boundaries
    if direction == 'up' and workout_index == 0:
        return False
    if direction == 'down' and workout_index == len(date_workouts) - 1:
        return False

    # Swap with adjacent workout
    if direction == 'up':
        date_workouts[workout_index], date_workouts[workout_index - 1] = \
            date_workouts[workout_index - 1], date_workouts[workout_index]
    else:  # down
        date_workouts[workout_index], date_workouts[workout_index + 1] = \
            date_workouts[workout_index + 1], date_workouts[workout_index]

    # Reassign order numbers
    for i, workout in enumerate(date_workouts):
        workout['Order'] = str(i + 1)

    # Get all workouts and replace the ones for this date
    all_workouts = read_workouts()
    other_workouts = [w for w in all_workouts if w['Date'] != target_date]

    # Combine and write back
    all_workouts = other_workouts + date_workouts

    with open(CSV_FILE, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(all_workouts)

    return True


# Upcoming workouts functions
def read_upcoming_workouts():
    """Read all upcoming workouts from CSV file."""
    if not UPCOMING_CSV_FILE.exists():
        return []

    workouts = []
    with open(UPCOMING_CSV_FILE, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            workouts.append(row)
    return workouts


def get_lowest_session_index():
    """Get the lowest session index from upcoming workouts."""
    workouts = read_upcoming_workouts()
    if not workouts:
        return None

    # Convert session to int and find minimum
    sessions = [int(w.get('Session', 0)) for w in workouts if w.get('Session', '').isdigit()]
    return min(sessions) if sessions else None


def pop_upcoming_workout_session(target_date):
    """
    Pop all exercises from the lowest session index and add them to historical workouts.
    Returns the number of exercises added.
    """
    upcoming = read_upcoming_workouts()
    if not upcoming:
        return 0

    # Find the lowest session index
    lowest_session = get_lowest_session_index()
    if lowest_session is None:
        return 0

    # Get workouts from the lowest session
    session_workouts = [w for w in upcoming if w.get('Session') == str(lowest_session)]
    remaining_workouts = [w for w in upcoming if w.get('Session') != str(lowest_session)]

    # Add session workouts to historical database
    for i, workout in enumerate(session_workouts):
        historical_workout = {
            'Date': target_date,
            'Exercise': workout.get('Exercise', ''),
            'Category': workout.get('Category', ''),
            'Weight': workout.get('Weight', ''),
            'Weight Unit': workout.get('Weight Unit', ''),
            'Reps': workout.get('Reps', ''),
            'Distance': workout.get('Distance', ''),
            'Distance Unit': workout.get('Distance Unit', ''),
            'Time': workout.get('Time', ''),
            'Comment': workout.get('Comment', ''),
            'Order': str(i + 1)  # Assign order based on position in session
        }
        write_workout(historical_workout)

    # Write remaining workouts back to upcoming file
    with open(UPCOMING_CSV_FILE, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=UPCOMING_CSV_HEADERS)
        writer.writeheader()
        writer.writerows(remaining_workouts)

    return len(session_workouts)


def calculate_estimated_1rm(weight, reps):
    """
    Calculate estimated 1RM using the formula: (0.033 × reps × weight) + weight

    Args:
        weight: Weight lifted
        reps: Number of reps (can be string like "5+" or int)

    Returns:
        Estimated 1RM value
    """
    try:
        # Handle reps like "5+" by extracting the number
        if isinstance(reps, str):
            reps_num = int(reps.replace('+', ''))
        else:
            reps_num = int(reps)

        weight_num = float(weight)

        # Formula: (0.033 × reps × weight) + weight
        estimated_1rm = (0.033 * reps_num * weight_num) + weight_num
        return estimated_1rm
    except (ValueError, TypeError):
        return 0


def get_progression_data(exercise_name):
    """
    Get progression data for a specific exercise including both historical and upcoming workouts.
    Maps ALL future sessions to projected dates based on 1 day on, 1 day off training schedule,
    then filters for the selected exercise.
    Calculates estimated 1RM for each set and returns the best set per session/date.
    Returns a dictionary with 'historical' and 'upcoming' lists.
    """
    from datetime import datetime, timedelta

    # Get historical workouts
    all_workouts = read_workouts()
    historical_raw = [w for w in all_workouts if w.get('Exercise') == exercise_name and w.get('Weight')]

    # Sort historical by date
    historical_raw.sort(key=lambda x: x.get('Date', ''))

    # Group historical by date and calculate best estimated 1RM per date
    historical_by_date = {}
    for workout in historical_raw:
        date = workout.get('Date', '')
        weight = workout.get('Weight', '')
        reps = workout.get('Reps', '')

        estimated_1rm = calculate_estimated_1rm(weight, reps)

        if date not in historical_by_date or estimated_1rm > historical_by_date[date]['estimated_1rm']:
            historical_by_date[date] = {
                'Date': date,
                'Exercise': workout.get('Exercise', ''),
                'Category': workout.get('Category', ''),
                'Weight': weight,
                'Weight Unit': workout.get('Weight Unit', ''),
                'Reps': reps,
                'Comment': workout.get('Comment', ''),
                'estimated_1rm': estimated_1rm
            }

    historical = list(historical_by_date.values())
    historical.sort(key=lambda x: x.get('Date', ''))

    # Get ALL upcoming workouts (not filtered by exercise yet)
    all_upcoming_workouts = read_upcoming_workouts()

    # First, create a mapping of ALL session numbers to dates
    # This is the absolute source of truth for date mapping
    all_sessions = {}
    for workout in all_upcoming_workouts:
        session = workout.get('Session', '')
        if session and session not in all_sessions:
            all_sessions[session] = []
        if session:
            all_sessions[session].append(workout)

    # Determine starting date for future sessions
    if historical:
        # Start from last historical workout date + 2 days
        last_date_str = historical[-1].get('Date', '')
        try:
            last_date = datetime.fromisoformat(last_date_str)
            start_date = last_date + timedelta(days=2)
        except (ValueError, TypeError):
            start_date = datetime.now(PACIFIC_TZ)
    else:
        # No historical data, start from today (Pacific time)
        start_date = datetime.now(PACIFIC_TZ)

    # Map ALL session numbers to dates (one date per session, regardless of exercise)
    session_to_date = {}
    current_date = start_date
    for session_num in sorted(all_sessions.keys(), key=lambda x: int(x) if x.isdigit() else 0):
        session_to_date[session_num] = current_date.isoformat()[:10]
        current_date += timedelta(days=2)  # Each session is 2 days apart

    # Now filter for the selected exercise and build the upcoming list
    upcoming = []
    for session_num in sorted(all_sessions.keys(), key=lambda x: int(x) if x.isdigit() else 0):
        session_workouts = all_sessions[session_num]

        # Filter this session's workouts for the selected exercise
        exercise_workouts = [w for w in session_workouts
                            if w.get('Exercise') == exercise_name and w.get('Weight')]

        if not exercise_workouts:
            continue  # This session doesn't have the selected exercise

        projected_date = session_to_date[session_num]

        # Find best set for this exercise in this session (highest estimated 1RM)
        best_workout = None
        best_estimated_1rm = 0

        for workout in exercise_workouts:
            weight = workout.get('Weight', '')
            reps = workout.get('Reps', '')
            estimated_1rm = calculate_estimated_1rm(weight, reps)

            if estimated_1rm > best_estimated_1rm:
                best_estimated_1rm = estimated_1rm
                best_workout = {
                    'Session': session_num,
                    'Exercise': workout.get('Exercise', ''),
                    'Category': workout.get('Category', ''),
                    'Weight': weight,
                    'Weight Unit': workout.get('Weight Unit', ''),
                    'Reps': reps,
                    'Comment': workout.get('Comment', ''),
                    'projected_date': projected_date,
                    'estimated_1rm': estimated_1rm
                }

        if best_workout:
            upcoming.append(best_workout)

    return {
        'historical': historical,
        'upcoming': upcoming
    }


def get_main_lifts():
    """Get list of all unique exercises for progression tracking."""
    # Get all unique exercises from historical workouts
    historical_exercises = set()
    workouts = read_workouts()
    for workout in workouts:
        exercise = workout.get('Exercise', '')
        if exercise:
            historical_exercises.add(exercise)

    # Get all unique exercises from upcoming workouts
    upcoming_exercises = set()
    upcoming = read_upcoming_workouts()
    for workout in upcoming:
        exercise = workout.get('Exercise', '')
        if exercise:
            upcoming_exercises.add(exercise)

    # Combine and sort
    all_exercises = sorted(list(historical_exercises | upcoming_exercises))
    return all_exercises if all_exercises else []
