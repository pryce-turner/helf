"""Body composition data management module."""
import csv
import os
from pathlib import Path
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

# Pacific timezone
PACIFIC_TZ = ZoneInfo("America/Los_Angeles")

# CSV file paths - use DATA_DIR environment variable or current directory
DATA_DIR = Path(os.getenv("DATA_DIR", "."))
CSV_FILE = DATA_DIR / "body_composition.csv"
CSV_HEADERS = ["Timestamp", "Date", "Weight", "Weight Unit", "Body Fat %",
               "Muscle Mass", "BMI", "Water %", "Bone Mass", "Visceral Fat",
               "Metabolic Age", "Protein %"]


def read_measurements():
    """Read all body composition measurements from CSV file."""
    if not CSV_FILE.exists():
        return []

    with open(CSV_FILE, 'r', newline='') as f:
        reader = csv.DictReader(f)
        return list(reader)


def write_measurement(timestamp, weight, weight_unit="kg", body_fat=None,
                      muscle_mass=None, bmi=None, water=None, bone_mass=None,
                      visceral_fat=None, metabolic_age=None, protein=None):
    """Write a new body composition measurement to CSV file.

    Ensures:
    - No duplicate measurements (based on timestamp)
    - Measurements are ordered by date/timestamp
    - Append-only operation (existing data not modified)
    """
    # Convert timestamp (Unix ms) to datetime in Pacific time
    if isinstance(timestamp, (int, float)):
        dt = datetime.fromtimestamp(timestamp / 1000, tz=PACIFIC_TZ)
    else:
        dt = datetime.now(PACIFIC_TZ)

    measurement_date = dt.date().isoformat()
    timestamp_str = dt.isoformat()

    # Read existing measurements
    existing_measurements = read_measurements()

    # Check for duplicate timestamp
    for existing in existing_measurements:
        if existing.get('Timestamp') == timestamp_str:
            # Measurement already exists, skip
            return False

    # Create the new measurement row
    new_row = {
        "Timestamp": timestamp_str,
        "Date": measurement_date,
        "Weight": weight,
        "Weight Unit": weight_unit,
        "Body Fat %": body_fat or "",
        "Muscle Mass": muscle_mass or "",
        "BMI": bmi or "",
        "Water %": water or "",
        "Bone Mass": bone_mass or "",
        "Visceral Fat": visceral_fat or "",
        "Metabolic Age": metabolic_age or "",
        "Protein %": protein or ""
    }

    # Add new measurement to list
    existing_measurements.append(new_row)

    # Sort by timestamp to ensure correct ordering
    existing_measurements.sort(key=lambda x: x['Timestamp'])

    # Write all measurements back to file (ordered and deduplicated)
    with open(CSV_FILE, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(existing_measurements)

    return True


def get_measurements_by_date(target_date):
    """Get all measurements for a specific date."""
    measurements = read_measurements()
    return [m for m in measurements if m['Date'] == target_date]


def get_date_range():
    """Get the earliest and latest measurement dates."""
    measurements = read_measurements()
    if not measurements:
        return None, None

    dates = [m['Date'] for m in measurements if m['Date']]
    if not dates:
        return None, None

    return min(dates), max(dates)


def get_latest_measurement():
    """Get the most recent measurement."""
    measurements = read_measurements()
    if not measurements:
        return None

    # Sort by timestamp descending
    sorted_measurements = sorted(
        measurements,
        key=lambda x: x['Timestamp'],
        reverse=True
    )
    return sorted_measurements[0]


def get_measurement_trend(days=30):
    """Get measurements for the last N days for trend analysis."""
    measurements = read_measurements()
    if not measurements:
        return []

    # Sort by timestamp
    sorted_measurements = sorted(
        measurements,
        key=lambda x: x['Timestamp']
    )

    # Filter by date range if needed
    if days:
        cutoff_date = (datetime.now(PACIFIC_TZ).date() - timedelta(days=days)).isoformat()
        sorted_measurements = [
            m for m in sorted_measurements
            if m['Date'] >= cutoff_date
        ]

    return sorted_measurements


def update_measurement(original, updated):
    """Update an existing measurement."""
    measurements = read_measurements()

    # Find and update the measurement
    found = False
    for i, m in enumerate(measurements):
        if m['Timestamp'] == original['Timestamp']:
            measurements[i] = updated
            found = True
            break

    if not found:
        return False

    # Write all measurements back
    with open(CSV_FILE, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(measurements)

    return True


def delete_measurement(measurement):
    """Delete a measurement."""
    measurements = read_measurements()

    # Filter out the measurement to delete
    measurements = [
        m for m in measurements
        if m['Timestamp'] != measurement['Timestamp']
    ]

    # Write remaining measurements back
    with open(CSV_FILE, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(measurements)


def get_stats_summary():
    """Get summary statistics for body composition metrics."""
    measurements = read_measurements()
    if not measurements:
        return {}

    latest = get_latest_measurement()
    if not latest:
        return {}

    def safe_float(value):
        try:
            return float(value) if value else None
        except (ValueError, TypeError):
            return None

    # Calculate 30-day average weight change (use Pacific time)
    now = datetime.now(PACIFIC_TZ)
    thirty_days_ago = now - timedelta(days=30)
    sixty_days_ago = now - timedelta(days=60)

    # Get measurements for last 30 days
    last_30_days = [
        m for m in measurements
        if datetime.fromisoformat(m['Timestamp']).replace(tzinfo=PACIFIC_TZ) >= thirty_days_ago
    ]

    # Get measurements for days 31-60
    prev_30_days = [
        m for m in measurements
        if sixty_days_ago <= datetime.fromisoformat(m['Timestamp']).replace(tzinfo=PACIFIC_TZ) < thirty_days_ago
    ]

    # Calculate average weight for each period
    def calculate_avg_weight(measurement_list):
        weights = [safe_float(m.get('Weight')) for m in measurement_list]
        weights = [w for w in weights if w is not None]
        return sum(weights) / len(weights) if weights else None

    avg_weight_last_30 = calculate_avg_weight(last_30_days)
    avg_weight_prev_30 = calculate_avg_weight(prev_30_days)

    # Calculate weight change (30-day average comparison)
    weight_change = None
    if avg_weight_last_30 is not None and avg_weight_prev_30 is not None:
        weight_change = avg_weight_last_30 - avg_weight_prev_30

    # Get first measurement for overall stats
    first = sorted(measurements, key=lambda x: x['Timestamp'])[0]

    return {
        'total_measurements': len(measurements),
        'latest_weight': safe_float(latest.get('Weight')),
        'latest_body_fat': safe_float(latest.get('Body Fat %')),
        'latest_muscle_mass': safe_float(latest.get('Muscle Mass')),
        'weight_change': weight_change,  # 30-day average change
        'body_fat_change': safe_float(latest.get('Body Fat %')) - safe_float(first.get('Body Fat %')) if safe_float(latest.get('Body Fat %')) and safe_float(first.get('Body Fat %')) else None,
        'muscle_mass_change': safe_float(latest.get('Muscle Mass')) - safe_float(first.get('Muscle Mass')) if safe_float(latest.get('Muscle Mass')) and safe_float(first.get('Muscle Mass')) else None,
        'first_date': first.get('Date'),
        'latest_date': latest.get('Date')
    }
