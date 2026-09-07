"""Index operations that remain disposable and rebuildable."""

import re
import sqlite3
from pathlib import Path

from .db import connect, initialize
from .models import Item
from .raw import parse


def index_document(connection: sqlite3.Connection, path: str, title: str, body: str) -> None:
    connection.execute("DELETE FROM docs_fts WHERE path = ?", (path,))
    connection.execute(
        "INSERT INTO docs_fts(path, title, body) VALUES (?, ?, ?)", (path, title, body)
    )


def index_item(connection: sqlite3.Connection, item: Item, path: str, body: str) -> None:
    connection.execute(
        """
        INSERT INTO items(id, source, path, title, ts, chars, built_at)
        VALUES (?, ?, ?, ?, ?, ?, NULL)
        ON CONFLICT(id) DO UPDATE SET
            source=excluded.source,
            path=excluded.path,
            title=excluded.title,
            ts=excluded.ts,
            chars=excluded.chars
        """,
        (item.id, item.source, path, item.title, item.ts, len(body)),
    )
    index_document(connection, path, item.title, body)


def reindex(vault_path: Path) -> tuple[int, int]:
    database = vault_path / "synapse.db"
    initialize(database)
    raw_count = 0
    page_count = 0
    with connect(database) as connection:
        connection.execute("DELETE FROM items")
        connection.execute("DELETE FROM docs_fts")
        connection.execute("DELETE FROM links")
        for path in sorted((vault_path / "raw").rglob("*.md")):
            item, body = parse(path)
            relative = path.relative_to(vault_path).as_posix()
            index_item(connection, item, relative, body)
            raw_count += 1
        for path in sorted((vault_path / "wiki").glob("*.md")):
            body = path.read_text(encoding="utf-8")
            match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
            title = match.group(1).strip() if match else path.stem
            index_document(connection, path.relative_to(vault_path).as_posix(), title, body)
            page_count += 1
    return raw_count, page_count


def _fts_query(query: str) -> str:
    tokens = re.findall(r"[\w-]+", query, re.UNICODE)
    return " AND ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)


def search(database: Path, query: str, limit: int = 10) -> list[dict[str, str]]:
    match = _fts_query(query)
    if not match:
        return []
    with connect(database) as connection:
        rows = connection.execute(
            """
            SELECT path, title, snippet(docs_fts, 2, '[', ']', ' … ', 20) AS snippet
            FROM docs_fts
            WHERE docs_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (match, limit),
        )
        return [dict(row) for row in rows]

