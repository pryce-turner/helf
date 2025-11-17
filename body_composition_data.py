"""Body composition data management module."""
import csv
import os
from pathlib import Path
from datetime import datetime, date

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
    """Write a new body composition measurement to CSV file."""
    # Convert timestamp (Unix ms) to datetime
    if isinstance(timestamp, (int, float)):
        dt = datetime.fromtimestamp(timestamp / 1000)
    else:
        dt = datetime.now()

    measurement_date = dt.date().isoformat()
    timestamp_str = dt.isoformat()

    # Check if file exists
    file_exists = CSV_FILE.exists()

    # Create the data row
    row = {
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

    # Check if we need to add a newline first
    needs_newline = False
    if file_exists and CSV_FILE.stat().st_size > 0:
        with open(CSV_FILE, 'rb') as f:
            f.seek(-1, 2)
            needs_newline = f.read(1) != b'\n'

    # Write the measurement
    with open(CSV_FILE, 'a', newline='') as f:
        if needs_newline:
            f.write('\n')

        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)

        # Write header if file is new
        if not file_exists or CSV_FILE.stat().st_size == 0:
            writer.writeheader()

        writer.writerow(row)


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
        cutoff_date = (datetime.now().date() - timedelta(days=days)).isoformat()
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

    # Calculate changes from first to latest
    first = sorted(measurements, key=lambda x: x['Timestamp'])[0]

    def safe_float(value):
        try:
            return float(value) if value else None
        except (ValueError, TypeError):
            return None

    def calculate_change(metric):
        first_val = safe_float(first.get(metric))
        latest_val = safe_float(latest.get(metric))
        if first_val is not None and latest_val is not None:
            return latest_val - first_val
        return None

    return {
        'total_measurements': len(measurements),
        'latest_weight': safe_float(latest.get('Weight')),
        'latest_body_fat': safe_float(latest.get('Body Fat %')),
        'latest_muscle_mass': safe_float(latest.get('Muscle Mass')),
        'weight_change': calculate_change('Weight'),
        'body_fat_change': calculate_change('Body Fat %'),
        'muscle_mass_change': calculate_change('Muscle Mass'),
        'first_date': first.get('Date'),
        'latest_date': latest.get('Date')
    }


from datetime import timedelta
