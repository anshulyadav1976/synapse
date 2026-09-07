"""Disposable SQLite indexing for a Synapse vault."""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    ts TEXT NOT NULL,
    chars INTEGER NOT NULL,
    built_at TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(path, title, body);
CREATE TABLE IF NOT EXISTS links (
    from_slug TEXT NOT NULL,
    to_slug TEXT NOT NULL,
    phrase TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (from_slug, to_slug)
);
"""


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def require_fts5(connection: sqlite3.Connection) -> None:
    try:
        connection.execute("CREATE VIRTUAL TABLE temp.fts5_check USING fts5(content)")
    except sqlite3.OperationalError as error:
        raise RuntimeError(
            "This Python installation was built without SQLite FTS5. "
            "Install Python 3.11+ from python.org or use a Python build with FTS5 enabled."
        ) from error


def initialize(path: Path) -> None:
    with connect(path) as connection:
        require_fts5(connection)
        connection.executescript(SCHEMA)

