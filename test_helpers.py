"""Reusable test helpers for a2a-skill test suite."""

import sqlite3
from pathlib import Path
from typing import Union


def make_connection(db_path: Union[str, Path]) -> sqlite3.Connection:
    """Open a SQLite connection with WAL journal mode and busy timeout applied.
    
    This is the WAL invariant: every database connection must set WAL mode
    and busy_timeout=5000 for concurrent-writer safety.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn
