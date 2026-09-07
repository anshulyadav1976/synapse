"""Readers for ordinary files and folders."""

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from ..models import Item
from . import adapter

TEXT_SUFFIXES = {
    ".csv",
    ".html",
    ".json",
    ".log",
    ".md",
    ".rst",
    ".text",
    ".toml",
    ".tsv",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}


def _timestamp(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()


def _id(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()[:24]


def _decode(path: Path) -> str:
    return path.read_bytes().decode("utf-8", errors="replace")


def _file_item(path: Path, label: str | None = None) -> Item:
    return Item(
        id=_id(label or str(path)),
        source="file",
        title=path.stem or path.name,
        ts=_timestamp(path),
        text=_decode(path),
    )


@adapter("file")
def read_file(path: Path) -> Iterator[Item]:
    # The replacement decoder is the universal fallback: unknown input still becomes searchable.
    yield from chunk_document(_file_item(path))


@adapter("dir")
def read_dir(path: Path) -> Iterator[Item]:
    for child in sorted(path.rglob("*")):
        if not child.is_file() or any(part.startswith(".") for part in child.relative_to(path).parts):
            continue
        if child.suffix.lower() not in TEXT_SUFFIXES:
            continue
        yield from chunk_document(_file_item(child, child.relative_to(path).as_posix()))


def chunk_document(item: Item, target: int = 7_000) -> Iterator[Item]:
    text = item.text or ""
    if len(text) <= target:
        yield item
        return

    sections: list[tuple[str, str]] = []
    heading = item.title
    body: list[str] = []
    for line in text.splitlines(keepends=True):
        if line.startswith("#") and line.lstrip("#").startswith(" ") and body:
            sections.append((heading, "".join(body)))
            heading = line.lstrip("# ").strip() or item.title
            body = [line]
        else:
            body.append(line)
    if body:
        sections.append((heading, "".join(body)))

    chunks: list[tuple[str, str]] = []
    current_title = item.title
    current = ""
    for section_title, section in sections:
        while len(section) > target:
            room = target - len(current)
            if room > 0:
                current += section[:room]
                section = section[room:]
            chunks.append((current_title, current))
            current_title, current = section_title, ""
        if current and len(current) + len(section) > target:
            chunks.append((current_title, current))
            current_title, current = section_title, section
        else:
            if not current:
                current_title = section_title
            current += section
    if current:
        chunks.append((current_title, current))

    for number, (title, body) in enumerate(chunks, 1):
        yield Item(
            id=f"{item.id}-chunk-{number}",
            source=item.source,
            title=f"{item.title} — {title}" if title != item.title else f"{item.title} — {number}",
            ts=item.ts,
            text=body,
            parent=item.id,
        )

