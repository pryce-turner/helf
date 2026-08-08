#!/usr/bin/env python3
"""Migration to add notes column to exercises table."""

import sqlite3
import sys
from pathlib import Path

# Default data directory
DATA_DIR = Path(__file__).parent.parent.parent / "data"


def migrate(db_path: Path) -> None:
    """Add notes column to exercises table if it doesn't exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if column already exists
    cursor.execute("PRAGMA table_info(exercises)")
    columns = [col[1] for col in cursor.fetchall()]

    if "notes" in columns:
        print("Column 'notes' already exists in exercises table.")
        conn.close()
        return

    # Add the notes column
    cursor.execute("ALTER TABLE exercises ADD COLUMN notes TEXT")
    conn.commit()
    print("Successfully added 'notes' column to exercises table.")

    conn.close()


if __name__ == "__main__":
    db_path = DATA_DIR / "helf.db"

    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])

    if not db_path.exists():
        print(f"Database not found at {db_path}")
        sys.exit(1)

    migrate(db_path)
