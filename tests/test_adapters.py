import json
from pathlib import Path
from zipfile import ZipFile

from synapse.adapters import detect, read
from synapse.adapters.files import chunk_document
from synapse.ingest import owner_chars
from synapse.models import Item, Turn

FIXTURES = Path(__file__).parent / "fixtures"
CHATGPT = FIXTURES / "chatgpt"


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

