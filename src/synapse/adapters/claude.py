"""Reader for claude.ai data exports (Settings → Privacy → Export data)."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZipFile

from ..models import Item, Turn
from . import adapter


def _iso(value: object) -> str | None:
    try:
        return datetime.fromisoformat(str(value)).astimezone(UTC).isoformat()
    except ValueError:
        return None


def _text(message: dict[str, Any]) -> str:
    # Newer exports split a reply into typed content blocks (text, tool_use, thinking...);
    # only the text blocks are conversation. Older ones carry a single flat `text` field.
    blocks = message.get("content")
    if isinstance(blocks, list):
        parts = [
            str(block.get("text") or "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        if any(parts):
            return "\n\n".join(part for part in parts if part).strip()
    return str(message.get("text") or "").strip()


def _conversation(data: dict[str, Any]) -> Item:
    identifier = str(data.get("uuid") or "")
    if not identifier:
        raise ValueError("A Claude conversation is missing its uuid")
    turns = []
    for message in data.get("chat_messages") or []:
        text = _text(message)
        if text:
            speaker = "me" if message.get("sender") == "human" else "claude"
            turns.append(Turn(speaker, text, _iso(message.get("created_at"))))
    return Item(
        id=identifier,
        source="claude",
        title=str(data.get("name") or "").strip() or "Untitled conversation",
        ts=_iso(data.get("created_at")) or datetime.fromtimestamp(0, UTC).isoformat(),
        turns=turns,
    )


def _items(conversations: list[dict[str, Any]]) -> Iterator[Item]:
    for conversation in conversations:
        yield _conversation(conversation)


@adapter("claude")
def read_claude(path: Path) -> Iterator[Item]:
    if path.is_dir():
        path = path / "conversations.json"
    if path.suffix.lower() == ".zip":
        with ZipFile(path) as archive:
            name = next(
                (name for name in archive.namelist() if PurePosixPath(name).name == "conversations.json"),
                None,
            )
            if name is None:
                raise ValueError(f"No conversations.json found in {path}. Is this a claude.ai data export?")
            yield from _items(json.loads(archive.read(name)))
        return
    if not path.is_file():
        raise ValueError(f"No conversations.json found at {path}. Pass the export zip or its unzipped folder.")
    yield from _items(json.loads(path.read_text(encoding="utf-8")))
