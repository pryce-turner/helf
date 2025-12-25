#!/usr/bin/env python3
"""
Migration script: CSV files → TinyDB

Migrates workout data from CSV files to TinyDB JSON database.
"""

import csv
import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tinydb import TinyDB
from tinydb.middlewares import CachingMiddleware
from tinydb.storages import JSONStorage

PACIFIC_TZ = ZoneInfo("America/Los_Angeles")


def parse_timestamp(timestamp_str: str) -> str:
    """Parse timestamp string to ISO format."""
    try:
        # Try parsing as ISO 8601
        dt = datetime.fromisoformat(timestamp_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=PACIFIC_TZ)
        return dt.isoformat()
    except ValueError:
        # If fails, assume it's just a date
        return timestamp_str


def migrate_workouts(csv_path: Path, db: TinyDB) -> int:
    """Migrate workouts.csv to TinyDB."""
    print(f"Migrating workouts from {csv_path}...")

    if not csv_path.exists():
        print(f"  ⚠️  File not found: {csv_path}")
        return 0

    table = db.table('workouts')
    count = 0

    with open(csv_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            # Parse and transform data
            doc = {
                'date': row.get('Date', ''),
                'exercise': row.get('Exercise', ''),
                'category': row.get('Category', ''),
                'weight': float(row['Weight']) if row.get('Weight') else None,
                'weight_unit': row.get('Weight Unit', 'lbs'),
                'reps': row.get('Reps', ''),  # Keep as string to handle "5+"
                'distance': float(row['Distance']) if row.get('Distance') else None,
                'distance_unit': row.get('Distance Unit') if row.get('Distance') else None,
                'time': row.get('Time') if row.get('Time') else None,
                'comment': row.get('Comment') if row.get('Comment') else None,
                'order': int(row['Order']) if row.get('Order') and row['Order'].isdigit() else 1,
                'created_at': parse_timestamp(row.get('Date', '')),
                'updated_at': parse_timestamp(row.get('Date', '')),
            }

            # Convert reps to int if possible, otherwise keep as string
            if doc['reps']:
                if doc['reps'].replace('+', '').isdigit():
                    if '+' in doc['reps']:
                        pass  # Keep as string like "5+"
                    else:
                        doc['reps'] = int(doc['reps'])
            else:
                doc['reps'] = None

            table.insert(doc)
            count += 1

    print(f"  ✓ Migrated {count} workouts")
    return count


def migrate_upcoming_workouts(csv_path: Path, db: TinyDB) -> int:
    """Migrate upcoming_workouts.csv to TinyDB."""
    print(f"Migrating upcoming workouts from {csv_path}...")

    if not csv_path.exists():
        print(f"  ⚠️  File not found: {csv_path}")
        return 0

    table = db.table('upcoming_workouts')
    count = 0

    with open(csv_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            doc = {
                'session': int(row['Session']) if row.get('Session', '').isdigit() else 0,
                'exercise': row.get('Exercise', ''),
                'category': row.get('Category', ''),
                'weight': float(row['Weight']) if row.get('Weight') else None,
                'weight_unit': row.get('Weight Unit', 'lbs'),
                'reps': row.get('Reps', ''),
                'distance': float(row['Distance']) if row.get('Distance') else None,
                'distance_unit': row.get('Distance Unit') if row.get('Distance') else None,
                'time': row.get('Time') if row.get('Time') else None,
                'comment': row.get('Comment') if row.get('Comment') else None,
                'created_at': datetime.now(PACIFIC_TZ).isoformat(),
            }

            # Convert reps to int if possible
            if doc['reps']:
                if doc['reps'].replace('+', '').isdigit():
                    if '+' not in doc['reps']:
                        doc['reps'] = int(doc['reps'])
            else:
                doc['reps'] = None

            table.insert(doc)
            count += 1

    print(f"  ✓ Migrated {count} upcoming workouts")
    return count


def migrate_body_composition(csv_path: Path, db: TinyDB) -> int:
    """Migrate body_composition.csv to TinyDB."""
    print(f"Migrating body composition from {csv_path}...")

    if not csv_path.exists():
        print(f"  ⚠️  File not found: {csv_path}")
        return 0

    table = db.table('body_composition')
    count = 0

    with open(csv_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            timestamp_str = row.get('Timestamp', '')

            doc = {
                'timestamp': parse_timestamp(timestamp_str),
                'date': row.get('Date', ''),
                'weight': float(row['Weight']) if row.get('Weight') else None,
                'weight_unit': row.get('Weight Unit', 'kg'),
                'body_fat_pct': float(row['Body Fat %']) if row.get('Body Fat %') else None,
                'muscle_mass': float(row['Muscle Mass']) if row.get('Muscle Mass') else None,
                'bmi': float(row['BMI']) if row.get('BMI') else None,
                'water_pct': float(row['Water %']) if row.get('Water %') else None,
                'bone_mass': float(row['Bone Mass']) if row.get('Bone Mass') else None,
                'visceral_fat': float(row['Visceral Fat']) if row.get('Visceral Fat') else None,
                'metabolic_age': int(row['Metabolic Age']) if row.get('Metabolic Age') else None,
                'protein_pct': float(row['Protein %']) if row.get('Protein %') else None,
                'created_at': parse_timestamp(timestamp_str),
            }

            table.insert(doc)
            count += 1

    print(f"  ✓ Migrated {count} body composition measurements")
    return count


def extract_exercises_and_categories(db: TinyDB) -> tuple[int, int]:
    """Extract unique exercises and categories from workouts."""
    print("Extracting exercises and categories...")

    workouts_table = db.table('workouts')
    upcoming_table = db.table('upcoming_workouts')
    exercises_table = db.table('exercises')
    categories_table = db.table('categories')

    # Get all workouts
    all_workouts = workouts_table.all() + upcoming_table.all()

    # Track exercises with their metadata
    exercises_data = {}  # {name: {category, last_used, count}}
    categories_set = set()

    for workout in all_workouts:
        exercise = workout.get('exercise', '')
        category = workout.get('category', '')
        date = workout.get('date', '')

        if not exercise or not category:
            continue

        categories_set.add(category)

        if exercise not in exercises_data:
            exercises_data[exercise] = {
                'category': category,
                'last_used': date,
                'count': 0
            }
        else:
            # Update last_used if this workout is more recent
            if date > exercises_data[exercise]['last_used']:
                exercises_data[exercise]['last_used'] = date

        exercises_data[exercise]['count'] += 1

    # Insert categories
    cat_count = 0
    for category in sorted(categories_set):
        categories_table.insert({
            'name': category,
            'created_at': datetime.now(PACIFIC_TZ).isoformat()
        })
        cat_count += 1

    # Insert exercises
    ex_count = 0
    for exercise_name, data in exercises_data.items():
        exercises_table.insert({
            'name': exercise_name,
            'category': data['category'],
            'last_used': data['last_used'],
            'use_count': data['count'],
            'created_at': datetime.now(PACIFIC_TZ).isoformat()
        })
        ex_count += 1

    print(f"  ✓ Extracted {ex_count} exercises and {cat_count} categories")
    return ex_count, cat_count


def main():
    """Run the migration."""
    print("=" * 60)
    print("CSV to TinyDB Migration")
    print("=" * 60)

    # Get paths
    data_dir = Path(__file__).parent.parent.parent / "data"
    db_path = data_dir / "helf.json"

    # Check if database already exists
    if db_path.exists():
        response = input(f"\n⚠️  Database {db_path} already exists. Overwrite? (y/N): ")
        if response.lower() != 'y':
            print("Migration cancelled.")
            return
        db_path.unlink()

    # Initialize database
    print(f"\nInitializing database at {db_path}...")
    db = TinyDB(
        db_path,
        storage=CachingMiddleware(JSONStorage),
        indent=2,
        ensure_ascii=False
    )

    # Run migrations
    print()
    totals = {
        'workouts': migrate_workouts(data_dir / "workouts.csv", db),
        'upcoming': migrate_upcoming_workouts(data_dir / "upcoming_workouts.csv", db),
        'body_comp': migrate_body_composition(data_dir / "body_composition.csv", db),
    }

    # Extract exercises and categories
    print()
    ex_count, cat_count = extract_exercises_and_categories(db)

    # Summary
    print()
    print("=" * 60)
    print("Migration Summary")
    print("=" * 60)
    print(f"Workouts:           {totals['workouts']:>6}")
    print(f"Upcoming workouts:  {totals['upcoming']:>6}")
    print(f"Body composition:   {totals['body_comp']:>6}")
    print(f"Exercises:          {ex_count:>6}")
    print(f"Categories:         {cat_count:>6}")
    print("=" * 60)
    print(f"✓ Migration complete! Database saved to {db_path}")

    # Close database
    db.close()


if __name__ == "__main__":
    main()
