"""Index operations that remain disposable and rebuildable."""

import re
import sqlite3
from datetime import datetime
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


SEARCH_STOP_WORDS = {
    "a", "about", "all", "an", "and", "any", "are", "at", "be", "by", "can", "could", "did", "do",
    "does", "for", "from", "get", "got", "had", "has", "have", "how", "i", "if", "in", "is", "it",
    "its", "me", "my", "now", "of", "on", "or", "our", "should", "so", "that", "the", "their",
    "them", "there", "this", "to", "us", "was", "we", "were", "what", "whats", "when", "where",
    "which", "who", "why", "will", "with", "would", "you", "your",
}
RECENCY_WEIGHT = 0.25  # up to +25% score for the newest candidate; relevance still dominates


def _tokens(query: str) -> list[str]:
    tokens = re.findall(r"[\w-]+", query, re.UNICODE)
    kept = [token for token in tokens if token.casefold() not in SEARCH_STOP_WORDS]
    return kept or tokens


def _quote(token: str) -> str:
    return '"' + token.replace(chr(34), chr(34) * 2) + '"'


def _fts_query(query: str, joiner: str = " AND ") -> str:
    return joiner.join(_quote(token) for token in _tokens(query))


def search(database: Path, query: str, limit: int = 10) -> list[dict[str, str]]:
    """Stemmed full-text search.

    Documents containing every meaningful word rank first; if that leaves room, documents
    matching only some words follow (best BM25 first), so a natural-language question or an
    extra word no longer returns nothing. Newer sources get a small boost so an update
    outranks the note it replaces.
    """
    strict, loose = _fts_query(query), _fts_query(query, " OR ")
    if not strict:
        return []
    pool = max(limit * 5, 50)
    sql = """
        SELECT docs_fts.path AS path, docs_fts.title AS title,
               snippet(docs_fts, 2, '[', ']', ' … ', 20) AS snippet,
               bm25(docs_fts, 0.0, 3.0, 1.0) AS score, items.ts AS ts
        FROM docs_fts LEFT JOIN items ON items.path = docs_fts.path
        WHERE docs_fts MATCH ?
        ORDER BY score
        LIMIT ?
    """
    with connect(database) as connection:
        tiers = [connection.execute(sql, (strict, pool)).fetchall()]
        if len(tiers[0]) < limit and loose != strict:
            tiers.append(connection.execute(sql, (loose, pool)).fetchall())
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for rows in tiers:
        dated = sorted(row["ts"] for row in rows if row["ts"])
        oldest, newest = (dated[0], dated[-1]) if dated else ("", "")

        def adjusted(row: sqlite3.Row) -> float:
            relevance = -row["score"]  # bm25 is negative; larger relevance is better
            if row["ts"] and newest > oldest:
                span = (datetime.fromisoformat(newest) - datetime.fromisoformat(oldest)).total_seconds()
                age = (datetime.fromisoformat(newest) - datetime.fromisoformat(row["ts"])).total_seconds()
                relevance *= 1 + RECENCY_WEIGHT * (1 - age / span)
            return relevance

        for row in sorted(rows, key=adjusted, reverse=True):
            if row["path"] in seen:
                continue
            seen.add(row["path"])
            result = {"path": row["path"], "title": row["title"], "snippet": row["snippet"]}
            if row["ts"]:
                result["date"] = row["ts"][:10]
            results.append(result)
            if len(results) >= limit:
                return results
    return results
