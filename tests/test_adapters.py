import json
from pathlib import Path
from zipfile import ZipFile

from synapse.adapters import detect, read
from synapse.adapters.files import chunk_document
from synapse.ingest import owner_chars
from synapse.models import Item, Turn

FIXTURES = Path(__file__).parent / "fixtures"
CHATGPT = FIXTURES / "chatgpt"
CLAUDE = FIXTURES / "claude"


def assert_chatgpt_item(path, format_name=None):
    items = list(read(path, format_name))
    assert len(items) == 1
    item = items[0]
    assert item.id == "synthetic-conversation-001"
    assert item.title == "Planning a tiny community garden"
    assert item.source == "chatgpt"
    assert [turn.speaker for turn in item.turns] == ["me", "assistant", "assistant"]
    assert "regenerated" in item.turns[-1].text


def test_chatgpt_folder_and_single_shard():
    assert detect(CHATGPT) == "chatgpt"
    assert_chatgpt_item(CHATGPT)
    assert_chatgpt_item(CHATGPT / "conversations-000.json")


def test_chatgpt_legacy_file(tmp_path):
    legacy = tmp_path / "conversations.json"
    legacy.write_bytes((CHATGPT / "conversations-000.json").read_bytes())
    assert_chatgpt_item(legacy)


def test_chatgpt_zip_uses_manifest(tmp_path):
    archive_path = tmp_path / "export.zip"
    with ZipFile(archive_path, "w") as archive:
        for source in CHATGPT.iterdir():
            archive.write(source, f"export/{source.name}")
    assert_chatgpt_item(archive_path)


def test_chatgpt_html_fallback(tmp_path):
    conversations = json.loads((CHATGPT / "conversations-000.json").read_text())
    html = tmp_path / "chat.html"
    html.write_text(
        "<html><script>var jsonData =" + json.dumps(conversations) + ";</script></html>"
    )
    assert_chatgpt_item(html)


def assert_claude_items(path):
    items = list(read(path))
    assert len(items) == 2
    first, second = items
    assert first.id == "synthetic-claude-001"
    assert first.source == "claude"
    assert first.title == "Sketching a bike shed rota"
    assert first.ts == "2026-03-01T09:00:00+00:00"
    assert [turn.speaker for turn in first.turns] == ["me", "claude"]
    assert first.turns[1].text == "Rotate alphabetically: Ada takes March."
    assert second.title == "Untitled conversation"
    assert [turn.text for turn in second.turns][-1] == "Flat replies still come through."


def test_claude_file_folder_and_zip(tmp_path):
    assert detect(CLAUDE) == "claude"
    assert detect(CLAUDE / "conversations.json") == "claude"
    assert_claude_items(CLAUDE)
    assert_claude_items(CLAUDE / "conversations.json")
    archive_path = tmp_path / "data-2026-04-03.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.write(CLAUDE / "conversations.json", "conversations.json")
        archive.writestr("users.json", "[]")
    assert detect(archive_path) == "claude"
    assert_claude_items(archive_path)


def test_legacy_chatgpt_conversations_json_is_not_claude(tmp_path):
    legacy = tmp_path / "conversations.json"
    legacy.write_bytes((CHATGPT / "conversations-000.json").read_bytes())
    assert detect(legacy) == "chatgpt"
    archive_path = tmp_path / "export.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.write(legacy, "conversations.json")
    assert detect(archive_path) == "chatgpt"


def test_file_dir_and_universal_fallback(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("hello searchable world")
    hidden = tmp_path / ".secret.txt"
    hidden.write_text("ignored")
    binary = tmp_path / "unknown.bin"
    binary.write_bytes(b"still\x80ingested")

    assert detect(note) == "file"
    assert [item.title for item in read(note)] == ["note"]
    assert [item.title for item in read(tmp_path)] == ["note"]
    assert "still" in next(read(binary)).text


def test_heading_chunking_and_trivia_count():
    item = Item("doc", "file", "Long note", "2026-01-01T00:00:00+00:00", text="# A\n" + "a" * 30 + "\n# B\n" + "b" * 30)
    chunks = list(chunk_document(item, target=35))
    assert len(chunks) == 2
    assert all(chunk.parent == "doc" for chunk in chunks)

    conversation = Item(
        "chat",
        "chatgpt",
        "Chat",
        "2026-01-01T00:00:00+00:00",
        turns=[Turn("me", "12345"), Turn("assistant", "x" * 100)],
    )
    assert owner_chars(conversation) == 5

