"""Reader for modern and legacy ChatGPT exports."""

import json
import mmap
import re
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZipFile

from ..models import Item, Turn
from . import adapter

SHARD = re.compile(r"conversations-\d+\.json$")


def _iso(value: object) -> str:
    try:
        return datetime.fromtimestamp(float(value), UTC).isoformat()
    except (TypeError, ValueError, OSError):
        return datetime.fromtimestamp(0, UTC).isoformat()


def _parts(content: dict[str, Any]) -> str:
    return "\n".join(part for part in content.get("parts", []) if isinstance(part, str)).strip()


def _conversation(data: dict[str, Any]) -> Item:
    messages: list[tuple[float, int, Turn]] = []
    for order, node in enumerate(data.get("mapping", {}).values()):
        message = node.get("message") or {}
        text = _parts(message.get("content") or {})
        if not text:
            continue
        author = message.get("author") or {}
        role = str(author.get("role") or "unknown")
        speaker = "me" if role == "user" else str(author.get("name") or role)
        created = message.get("create_time")
        messages.append((float(created or 0), order, Turn(speaker, text, _iso(created))))
    messages.sort(key=lambda entry: (entry[0], entry[1]))
    identifier = str(data.get("conversation_id") or data.get("id") or "")
    if not identifier:
        raise ValueError("A ChatGPT conversation is missing both conversation_id and id")
    return Item(
        id=identifier,
        source="chatgpt",
        title=str(data.get("title") or "Untitled conversation"),
        ts=_iso(data.get("create_time")),
        turns=[entry[2] for entry in messages],
    )


def _items(conversations: Iterable[dict[str, Any]]) -> Iterator[Item]:
    for conversation in conversations:
        yield _conversation(conversation)


def _manifest_files(data: dict[str, Any]) -> list[str]:
    return [
        str(entry["path"])
        for entry in data.get("export_files", [])
        if isinstance(entry, dict)
        and "path" in entry
        and (SHARD.search(str(entry["path"])) or PurePosixPath(str(entry["path"])).name == "conversations.json")
    ]


def _folder_files(path: Path) -> list[Path]:
    manifest = path / "export_manifest.json"
    if manifest.exists():
        names = _manifest_files(json.loads(manifest.read_text(encoding="utf-8")))
        found = [path / name for name in names if (path / name).is_file()]
        if found:
            return found
    shards = sorted(path.glob("conversations-*.json"))
    if shards:
        return shards
    legacy = path / "conversations.json"
    return [legacy] if legacy.exists() else []


def _from_html_bytes(data: bytes, label: str) -> Iterator[Item]:
    marker = b"var jsonData ="
    start = data.find(marker)
    if start < 0:
        raise ValueError(f"No 'var jsonData =' conversation payload found in {label}")
    start += len(marker)
    end = data.find(b";</script>", start)
    if end < 0:
        end = data.find(b";\n", start)
    if end < 0:
        raise ValueError(f"The ChatGPT payload in {label} has no closing semicolon")
    yield from _items(json.loads(data[start:end]))


def _from_html(path: Path) -> Iterator[Item]:
    with path.open("rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
        yield from _from_html_bytes(data, str(path))


def _from_zip(path: Path) -> Iterator[Item]:
    with ZipFile(path) as archive:
        names = archive.namelist()
        manifest_name = next((name for name in names if PurePosixPath(name).name == "export_manifest.json"), None)
        selected: list[str] = []
        if manifest_name:
            manifest = json.loads(archive.read(manifest_name))
            base = PurePosixPath(manifest_name).parent
            available = set(names)
            selected = [str(base / name) for name in _manifest_files(manifest) if str(base / name) in available]
        if not selected:
            selected = sorted(
                name
                for name in names
                if SHARD.search(PurePosixPath(name).name)
                or PurePosixPath(name).name == "conversations.json"
            )
        if selected:
            for name in selected:
                yield from _items(json.loads(archive.read(name)))
            return
        html = next((name for name in names if PurePosixPath(name).name == "chat.html"), None)
        if html:
            yield from _from_html_bytes(archive.read(html), f"{path}!{html}")
            return
    raise ValueError(f"No ChatGPT conversations found in {path}")


@adapter("chatgpt")
def read_chatgpt(path: Path) -> Iterator[Item]:
    if path.is_dir():
        files = _folder_files(path)
        if not files:
            html = path / "chat.html"
            if html.exists():
                yield from _from_html(html)
                return
            raise ValueError(
                f"No conversations found in {path}. Modern exports shard them as "
                "conversations-000.json; pass --format chatgpt to force detection."
            )
        for file in files:
            yield from _items(json.loads(file.read_text(encoding="utf-8")))
        return
    if path.suffix.lower() == ".zip":
        yield from _from_zip(path)
    elif path.name == "chat.html":
        yield from _from_html(path)
    else:
        yield from _items(json.loads(path.read_text(encoding="utf-8")))

