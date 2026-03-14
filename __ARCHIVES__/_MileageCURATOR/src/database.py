import sqlite3
import os
from pathlib import Path

def get_db_connection(project_dir: Path):
    """Establishes and returns a connection to the SQLite database inside the project workspace."""
    db_path = project_dir / 'mileage.db'
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(project_dir: Path):
    """Initializes the database schema if it doesn't exist in the project workspace."""
    conn = get_db_connection(project_dir)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            start_lat REAL NOT NULL,
            start_lng REAL NOT NULL,
            end_lat REAL NOT NULL,
            end_lng REAL NOT NULL,
            distance_miles REAL NOT NULL,
            category TEXT DEFAULT 'Unknown',
            notes TEXT DEFAULT ''
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database initialized successfully.")

if __name__ == "__main__":
    # Test with a dummy project dir
    test_dir = Path('../workspaces/test_project')
    test_dir.mkdir(parents=True, exist_ok=True)
    init_db(test_dir)
