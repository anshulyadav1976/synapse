"""Small reader registry: every input format stops at Item."""

import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TypeAlias
from zipfile import BadZipFile, ZipFile

from ..models import Item

Reader: TypeAlias = Callable[[Path], Iterator[Item]]
READERS: dict[str, Reader] = {}


def adapter(name: str) -> Callable[[Reader], Reader]:
    def register(reader: Reader) -> Reader:
        READERS[name] = reader
        return reader

    return register


def _zip_names(path: Path) -> list[str]:
    try:
        with ZipFile(path) as archive:
            return archive.namelist()
    except (BadZipFile, OSError):
        return []


CLAUDE_KEY = re.compile(rb'(?:^|[,{])\s*"chat_messages"\s*:')
CHATGPT_KEY = re.compile(rb'(?:^|[,{])\s*"mapping"\s*:')


def _is_claude(head: bytes) -> bool:
    # ChatGPT's legacy export and claude.ai's both name the file conversations.json;
    # the first conversation's keys tell them apart without parsing the whole file.
    messages, mapping = CLAUDE_KEY.search(head), CHATGPT_KEY.search(head)
    return messages is not None and (mapping is None or messages.start() < mapping.start())


def _head(path: Path, size: int = 65536) -> bytes:
    with path.open("rb") as handle:
        return handle.read(size)


def _zip_head(path: Path, name: str, size: int = 65536) -> bytes:
    with ZipFile(path) as archive, archive.open(name) as handle:
        return handle.read(size)


def detect(path: Path) -> str:
    if path.is_dir():
        names = {child.name for child in path.iterdir()}
        if "conversations.json" in names and _is_claude(_head(path / "conversations.json")):
            return "claude"
        if "export_manifest.json" in names or any(
            name.startswith("conversations-") and name.endswith(".json") for name in names
        ):
            return "chatgpt"
        return "dir"
    if path.name == "conversations.json" and _is_claude(_head(path)):
        return "claude"
    if path.name == "conversations.json" or (
        path.name.startswith("conversations-") and path.suffix == ".json"
    ):
        return "chatgpt"
    if path.name == "chat.html":
        return "chatgpt"
    if path.suffix.lower() == ".zip":
        names = _zip_names(path)
        listing = next((name for name in names if Path(name).name == "conversations.json"), None)
        if listing and _is_claude(_zip_head(path, listing)):
            return "claude"
        if any(
            Path(name).name == "export_manifest.json"
            or Path(name).name == "conversations.json"
            or Path(name).name == "chat.html"
            or (Path(name).name.startswith("conversations-") and name.endswith(".json"))
            for name in names
        ):
            return "chatgpt"
    return "file"


def read(path: str | Path, format_name: str | None = None) -> Iterator[Item]:
    source = Path(path).expanduser().resolve()
    name = format_name or detect(source)
    try:
        reader = READERS[name]
    except KeyError as error:
        choices = ", ".join(sorted(READERS))
        raise ValueError(f"Unknown format {name!r}. Available formats: {choices}") from error
    yield from reader(source)


# Importing registers the built-in readers while keeping contributor adapters tiny.
from . import chatgpt, claude, files  # noqa: F401
