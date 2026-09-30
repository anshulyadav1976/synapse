"""Optional semantic index derived from the Markdown vault."""

import hashlib
import math
import sys
from array import array
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from .db import connect


@dataclass(frozen=True)
class EmbeddingEstimate:
    documents: int
    chunks: int
    pending_chunks: int
    input_tokens: int


@dataclass(frozen=True)
class EmbeddingResult:
    documents: int
    chunks: int
    embedded_chunks: int
    skipped_chunks: int


@dataclass(frozen=True)
class _Chunk:
    path: str
    number: int
    text: str
    digest: str


def _documents(vault_path: Path, include_raw: bool) -> Iterator[tuple[str, str]]:
    roots = [vault_path / "wiki", vault_path / "notes"]
    if include_raw:
        roots.append(vault_path / "raw")
    for root in roots:
        for path in sorted(root.rglob("*.md")):
            if path.name.startswith("."):
                continue
            yield path.relative_to(vault_path).as_posix(), path.read_text(encoding="utf-8")


def _split(text: str, size: int = 6000) -> list[str]:
    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        while len(paragraph) > size:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(paragraph[:size])
            paragraph = paragraph[size:]
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) > size:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _plan(vault_path: Path, include_raw: bool) -> tuple[int, list[_Chunk]]:
    documents = 0
    chunks: list[_Chunk] = []
    for path, text in _documents(vault_path, include_raw):
        documents += 1
        for number, chunk in enumerate(_split(text)):
            digest = hashlib.sha256(chunk.encode()).hexdigest()
            chunks.append(_Chunk(path, number, chunk, digest))
    return documents, chunks


def estimate_embeddings(
    vault_path: Path, database: Path, model: str, include_raw: bool = False
) -> EmbeddingEstimate:
    documents, chunks = _plan(vault_path, include_raw)
    with connect(database) as connection:
        existing = {
            (row["path"], row["chunk"]): row["content_hash"]
            for row in connection.execute(
                "SELECT path, chunk, content_hash FROM embeddings WHERE model = ?", (model,)
            )
        }
    pending = [chunk for chunk in chunks if existing.get((chunk.path, chunk.number)) != chunk.digest]
    return EmbeddingEstimate(
        documents,
        len(chunks),
        len(pending),
        sum((len(chunk.text) + 3) // 4 for chunk in pending),
    )


def build_embeddings(
    vault_path: Path,
    database: Path,
    model: str,
    embed: Callable[[list[str]], list[list[float]]],
    include_raw: bool = False,
    batch_size: int = 32,
) -> EmbeddingResult:
    documents, chunks = _plan(vault_path, include_raw)
    with connect(database) as connection:
        existing = {
            (row["path"], row["chunk"]): row["content_hash"]
            for row in connection.execute(
                "SELECT path, chunk, content_hash FROM embeddings WHERE model = ?", (model,)
            )
        }
    pending = [chunk for chunk in chunks if existing.get((chunk.path, chunk.number)) != chunk.digest]
    current = {(chunk.path, chunk.number): chunk.digest for chunk in chunks}
    selected = ("raw/", "wiki/", "notes/") if include_raw else ("wiki/", "notes/")
    with connect(database) as connection:
        for row in connection.execute(
            "SELECT path, chunk, content_hash FROM embeddings WHERE model = ?", (model,)
        ).fetchall():
            key = (row["path"], row["chunk"])
            if row["path"].startswith(selected) and current.get(key) != row["content_hash"]:
                connection.execute(
                    "DELETE FROM embeddings WHERE path = ? AND chunk = ? AND model = ?",
                    (row["path"], row["chunk"], model),
                )

    written = 0
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        vectors = embed([chunk.text for chunk in batch])
        if len(vectors) != len(batch):
            raise RuntimeError("Embedding endpoint returned the wrong number of vectors")
        packed = [(chunk, *_pack(vector)) for chunk, vector in zip(batch, vectors, strict=True)]
        with connect(database) as connection:
            for chunk, vector, dimensions in packed:
                connection.execute(
                    """
                    INSERT INTO embeddings(path, chunk, content_hash, model, dimensions, vector, text)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(path, chunk, model) DO UPDATE SET
                        content_hash=excluded.content_hash,
                        dimensions=excluded.dimensions,
                        vector=excluded.vector,
                        text=excluded.text
                    """,
                    (
                        chunk.path,
                        chunk.number,
                        chunk.digest,
                        model,
                        dimensions,
                        vector,
                        chunk.text,
                    ),
                )
        written += len(batch)
    return EmbeddingResult(documents, len(chunks), written, len(chunks) - written)


def _normalise(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if not vector or not math.isfinite(magnitude) or magnitude == 0:
        raise RuntimeError("Embedding endpoint returned an invalid zero-length vector")
    return [value / magnitude for value in vector]


def _pack(vector: list[float]) -> tuple[bytes, int]:
    values = array("f", _normalise(vector))
    if sys.byteorder != "little":
        values.byteswap()
    return values.tobytes(), len(values)


def _unpack(blob: bytes, dimensions: int) -> array:
    values = array("f")
    values.frombytes(blob)
    if sys.byteorder != "little":
        values.byteswap()
    if len(values) != dimensions:
        raise RuntimeError("Semantic index is corrupt; run: synapse embed")
    return values


def semantic_search(
    database: Path,
    vector: list[float],
    model: str,
    limit: int,
    *,
    after: str | None = None,
    before: str | None = None,
    source: str | None = None,
    kind: str | None = None,
) -> list[dict[str, str]]:
    query = _normalise(vector)
    conditions = ["e.model = ?"]
    parameters: list[object] = [model]
    if after:
        conditions.append("i.ts >= ?")
        parameters.append(after)
    if before:
        conditions.append("i.ts < ?")
        parameters.append(before)
    if source:
        conditions.append("i.source = ?")
        parameters.append(source)
    if kind:
        prefix = {"raw": "raw/%", "wiki": "wiki/%", "note": "notes/%"}[kind]
        conditions.append("e.path LIKE ?")
        parameters.append(prefix)
    sql = f"""
        SELECT e.path, e.text, e.dimensions, e.vector,
               docs_fts.title AS title, items.ts AS ts
        FROM embeddings AS e
        JOIN docs_fts ON docs_fts.path = e.path
        LEFT JOIN items ON items.path = e.path
        WHERE {' AND '.join(conditions)}
    """
    best: dict[str, tuple[float, dict[str, str]]] = {}
    with connect(database) as connection:
        rows = connection.execute(sql, parameters).fetchall()
    # ponytail: exact scan keeps the package portable; add a native index only after measured pain.
    for row in rows:
        stored = _unpack(row["vector"], row["dimensions"])
        if len(stored) != len(query):
            raise RuntimeError("Embedding dimensions changed; run: synapse embed")
        score = sum(left * right for left, right in zip(stored, query, strict=True))
        snippet = " ".join(row["text"].split())[:240]
        result = {"path": row["path"], "title": row["title"], "snippet": snippet}
        if row["ts"]:
            result["date"] = row["ts"][:10]
        if row["path"] not in best or score > best[row["path"]][0]:
            best[row["path"]] = (score, result)
    ranked = sorted(best.values(), key=lambda item: item[0], reverse=True)[:limit]
    return [result for _, result in ranked]
