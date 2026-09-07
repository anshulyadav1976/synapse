"""Human-readable, round-trippable raw Markdown."""

import hashlib
import json
import re
from pathlib import Path

from .models import Item

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
    }
    lines = ["---", json.dumps(metadata, ensure_ascii=False, separators=(",", ":")), "---", ""]
    lines.extend([f"# {item.title}", ""])
    if item.turns is not None:
        for turn in item.turns:
            timestamp = f" — {turn.ts}" if turn.ts else ""
            lines.extend([f"### {turn.speaker}{timestamp}", "", turn.text, ""])
    elif item.text:
        lines.extend([item.text, ""])
    return "\n".join(lines).rstrip() + "\n"


def parse(path: Path) -> tuple[Item, str]:
    document = path.read_text(encoding="utf-8")
    lines = document.splitlines()
    if len(lines) < 3 or lines[0] != "---" or lines[2] != "---":
        raise ValueError(f"Raw item {path} has invalid Synapse metadata")
    metadata = json.loads(lines[1])
    body = "\n".join(lines[3:]).lstrip()
    return (
        Item(
            id=metadata["id"],
            source=metadata["source"],
            title=metadata["title"],
            ts=metadata["ts"],
            text=body,
            parent=metadata.get("parent"),
        ),
        document,
    )

