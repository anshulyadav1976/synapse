"""The only data shape adapters expose to the rest of Synapse."""

from dataclasses import dataclass


@dataclass
class Turn:
    speaker: str
    text: str
    ts: str | None = None


@dataclass
class Item:
    id: str
    source: str
    title: str
    ts: str
    text: str | None = None
    turns: list[Turn] | None = None
    parent: str | None = None

