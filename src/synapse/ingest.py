"""Free ingest path: adapter to immutable Markdown to FTS5."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .adapters import detect, read
from .db import connect
from .index import index_item
from .models import Item
from .raw import filename, parse, render
from .vault import Vault


@dataclass
class IngestResult:
    format: str
    seen: int = 0
    added: int = 0
    skipped: int = 0
    filtered: int = 0


def owner_chars(item: Item, owner: str = "") -> int:
    owners = {"me", "user"}
    owners.update(alias.strip().casefold() for alias in owner.split(",") if alias.strip())
    return sum(
        len(turn.text) for turn in item.turns or [] if turn.speaker.casefold() in owners
    )


def _month(timestamp: str) -> str:
    try:
        return datetime.fromisoformat(timestamp).strftime("%Y-%m")
    except ValueError:
        return "unknown-date"


def ingest(
    vault: Vault,
    input_path: str | Path,
    format_name: str | None = None,
    min_chars: int = 200,
    owner: str = "",
    progress: Callable[[IngestResult], None] | None = None,
) -> IngestResult:
    if not vault.db_path.exists():
        raise FileNotFoundError(f"No vault at {vault.path}. Run: synapse init {vault.path}")
    source = Path(input_path).expanduser().resolve()
    selected = format_name or detect(source)
    result = IngestResult(selected)
    with connect(vault.db_path) as connection:
        for item in read(source, selected):
            result.seen += 1
            if item.turns is not None and owner_chars(item, owner) < min_chars:
                result.filtered += 1
                if progress:
                    progress(result)
                continue
            relative = Path("raw") / item.source / _month(item.ts) / f"{filename(item.id)}.md"
            destination = vault.path / relative
            if destination.exists():
                existing, body = parse(destination)
                index_item(connection, existing, relative.as_posix(), body)
                result.skipped += 1
                if progress:
                    progress(result)
                continue
            body = render(item)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(body, encoding="utf-8")
            index_item(connection, item, relative.as_posix(), body)
            result.added += 1
            if progress:
                progress(result)
    return result
