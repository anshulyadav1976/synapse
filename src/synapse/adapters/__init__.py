"""Small reader registry: every input format stops at Item."""

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


def detect(path: Path) -> str:
    if path.is_dir():
        names = {child.name for child in path.iterdir()}
        if "export_manifest.json" in names or any(
            name.startswith("conversations-") and name.endswith(".json") for name in names
        ):
            return "chatgpt"
        return "dir"
    if path.name == "conversations.json" or (
        path.name.startswith("conversations-") and path.suffix == ".json"
    ):
        return "chatgpt"
    if path.name == "chat.html":
        return "chatgpt"
    if path.suffix.lower() == ".zip":
        names = _zip_names(path)
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
from . import chatgpt, files  # noqa: F401
