"""Human-readable, round-trippable raw Markdown."""

import hashlib
import json
import re
from pathlib import Path

from .models import Item, Turn

SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")


def filename(identifier: str) -> str:
    if SAFE_NAME.fullmatch(identifier):
        return identifier
    return hashlib.sha256(identifier.encode()).hexdigest()[:32]


def render(item: Item) -> str:
    metadata = {
        "id": item.id,
        "source": item.source,
        "title": item.title,
        "ts": item.ts,
        "parent": item.parent,
        "kind": "conversation" if item.turns is not None else "document",
    }
    lines = ["---", json.dumps(metadata, ensure_ascii=False, separators=(",", ":")), "---", ""]
    lines.extend([f"# {item.title}", ""])
    if item.turns is not None:
        for turn in item.turns:
            timestamp = f" — {turn.ts}" if turn.ts else ""
            marker = json.dumps(
                {"speaker": turn.speaker, "ts": turn.ts},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            lines.extend(
                [f"<!-- synapse-turn {marker} -->", f"### {turn.speaker}{timestamp}", "", turn.text, ""]
            )
    elif item.text:
        lines.extend([item.text, ""])
    return "\n".join(lines).rstrip() + "\n"


def parse(path: Path) -> tuple[Item, str]:
    document = path.read_text(encoding="utf-8")
    lines = document.splitlines()
    if len(lines) < 3 or lines[0] != "---" or lines[2] != "---":
        raise ValueError(f"Raw item {path} has invalid Synapse metadata")
    metadata = json.loads(lines[1])
    body_lines = lines[3:]
    body = "\n".join(body_lines).lstrip()
    turns = _parse_turns(body_lines) if metadata.get("kind") == "conversation" else None
    if "kind" not in metadata and any(line.startswith("### ") for line in body_lines):
        turns = _parse_turns(body_lines)
    return (
        Item(
            id=metadata["id"],
            source=metadata["source"],
            title=metadata["title"],
            ts=metadata["ts"],
            text=None if turns is not None else body,
            turns=turns,
            parent=metadata.get("parent"),
        ),
        document,
    )


def _parse_turns(lines: list[str]) -> list[Turn]:
    turns: list[Turn] = []
    current: Turn | None = None
    body: list[str] = []
    marker = re.compile(r"^<!-- synapse-turn (.+) -->$")
    heading = re.compile(r"^### (.+?)(?: — (.+))?$")

    def finish() -> None:
        if current is not None:
            current.text = "\n".join(body).strip()
            turns.append(current)

    pending: dict[str, str | None] | None = None
    for line in lines:
        marked = marker.match(line)
        if marked:
            pending = json.loads(marked.group(1))
            continue
        header = heading.match(line)
        if header and (pending is not None or current is not None or not turns):
            finish()
            current = Turn(
                str(pending["speaker"]) if pending else header.group(1),
                "",
                pending.get("ts") if pending else header.group(2),
            )
            pending = None
            body = []
        elif current is not None:
            body.append(line)
    finish()
    return turns
