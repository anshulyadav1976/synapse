# Add an adapter

An adapter does one job: turn an input into a stream of `Item` objects. It never writes Markdown, touches SQLite, calls a model, or decides what a fact means.

Here is a complete small reader for a synthetic line-based chat format:

```python
import hashlib
from collections.abc import Iterator
from pathlib import Path

from synapse.adapters import adapter
from synapse.models import Item, Turn


@adapter("tinychat")
def read_tinychat(path: Path) -> Iterator[Item]:
    turns = []
    for line in path.read_text(encoding="utf-8").splitlines():
        timestamp, speaker, text = line.split(" | ", 2)
        turns.append(Turn(speaker=speaker, text=text, ts=timestamp))

    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:24]
    yield Item(
        id=digest,
        source="tinychat",
        title=path.stem,
        ts=turns[0].ts,
        turns=turns,
    )
```

Then import the module at the bottom of `synapse/adapters/__init__.py` so the decorator registers it, and add detection only when the format has a reliable signature. `--format tinychat` works without detection.

## The contract

- `id` stays stable across reruns. Hash source bytes or use a source-provided immutable ID.
- `source` is a short lowercase folder name.
- `title` is for humans, not identity.
- `ts` is a real ISO 8601 timestamp. Do not ask a model to infer it.
- Use `text` for documents or `turns` for conversations.
- Use `parent` when a large document is split into chunks.
- Stream with an iterator; do not load a whole export when files can be processed one at a time.

Adapters preserve boundaries, timestamps, and speakers because those are deterministic in source formats and expensive to recover later. Unknown files still go through the universal text fallback, so adding an adapter improves structure rather than deciding whether data is accepted.

## The test

Add one tiny, obviously synthetic fixture and assert the item count plus the fields the format promises:

```python
def test_tinychat_fixture():
    items = list(read("tests/fixtures/tinychat.txt", "tinychat"))
    assert len(items) == 1
    assert items[0].source == "tinychat"
    assert [turn.speaker for turn in items[0].turns] == ["Ada", "Bot"]
```

Never use your real export as a fixture. If a parser needs an edge case, reproduce only its structure with invented names and text.
