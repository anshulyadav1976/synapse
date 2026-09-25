"""Index operations that remain disposable and rebuildable."""

import re
import sqlite3
from pathlib import Path

from .db import connect, initialize
from .models import Item
from .raw import parse

WIKILINK = re.compile(r"\[\[([a-z0-9][a-z0-9-]{0,60})\]\]")
RELATED_LINE = re.compile(
    r"^\s*-\s*\[\[([a-z0-9][a-z0-9-]{0,60})\]\]\s*(?:[—-]\s*)?(.*)$"
)
SOURCE_LINE = re.compile(r"^\s*-\s*(raw/\S+\.md)\s*$")
BUILD_RECEIPT = re.compile(r"^\s*-\s*\[([^]]+)\]\s+(raw/\S+\.md)\s*$")


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


def wikilinks(body: str) -> list[tuple[str, str]]:
    phrases = {
        match.group(1): match.group(2).strip()
        for line in body.splitlines()
        if (match := RELATED_LINE.match(line))
    }
    return [(slug, phrases.get(slug, "")) for slug in dict.fromkeys(WIKILINK.findall(body))]


def replace_links(connection: sqlite3.Connection, from_slug: str, body: str) -> None:
    connection.execute("DELETE FROM links WHERE from_slug = ?", (from_slug,))
    connection.executemany(
        "INSERT INTO links(from_slug, to_slug, phrase) VALUES (?, ?, ?)",
        [(from_slug, to_slug, phrase) for to_slug, phrase in wikilinks(body)],
    )


def reindex(vault_path: Path) -> tuple[int, int, int]:
    database = vault_path / "synapse.db"
    initialize(database)
    raw_count = 0
    page_count = 0
    note_count = 0
    with connect(database) as connection:
        connection.execute("DELETE FROM items")
        connection.execute("DELETE FROM docs_fts")
        connection.execute("DELETE FROM links")
        for path in sorted((vault_path / "raw").rglob("*.md")):
            item, body = parse(path)
            relative = path.relative_to(vault_path).as_posix()
            index_item(connection, item, relative, body)
            raw_count += 1
        build_log = vault_path / "wiki" / ".synapse-built.md"
        if build_log.exists():
            for line in build_log.read_text(encoding="utf-8").splitlines():
                if receipt := BUILD_RECEIPT.match(line):
                    connection.execute(
                        "UPDATE items SET built_at = ? WHERE path = ?",
                        (receipt.group(1), receipt.group(2)),
                    )
        for path in sorted((vault_path / "wiki").glob("*.md")):
            if path.name.startswith("."):
                continue
            body = path.read_text(encoding="utf-8")
            match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
            title = match.group(1).strip() if match else path.stem
            index_document(connection, path.relative_to(vault_path).as_posix(), title, body)
            replace_links(connection, path.stem, body)
            for line in body.splitlines():
                if source := SOURCE_LINE.match(line):
                    connection.execute(
                        "UPDATE items SET built_at = 'indexed' WHERE path = ?", (source.group(1),)
                    )
            page_count += 1
        for path in sorted((vault_path / "notes").glob("*.md")):
            body = path.read_text(encoding="utf-8")
            match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
            title = match.group(1).strip() if match else path.stem
            index_document(connection, path.relative_to(vault_path).as_posix(), title, body)
            note_count += 1
    return raw_count, page_count, note_count


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
