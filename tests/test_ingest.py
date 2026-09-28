from pathlib import Path

from synapse import Vault
from synapse.db import connect, search_index_needs_rebuild
from synapse.index import reindex
from synapse.ingest import ingest

FIXTURES = Path(__file__).parent / "fixtures"


def test_ingest_is_write_once_searchable_and_reindexable(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()

    result = ingest(vault, FIXTURES / "chatgpt", min_chars=10)
    assert (result.seen, result.added, result.skipped, result.filtered) == (1, 1, 0, 0)
    raw = list(vault.raw_path.rglob("*.md"))
    assert len(raw) == 1
    original = raw[0].read_text()
    assert vault.search("community garden")[0]["path"].startswith("raw/chatgpt/")

    repeated = ingest(vault, FIXTURES / "chatgpt", min_chars=10)
    assert repeated.added == 0
    assert repeated.skipped == 1
    assert raw[0].read_text() == original

    vault.db_path.unlink()
    assert reindex(vault.path) == (1, 0, 0)
    assert vault.search("community garden")


def test_trivia_filter(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()
    result = ingest(vault, FIXTURES / "chatgpt", min_chars=200)
    assert result.seen == 1
    assert result.filtered == 1
    assert result.added == 0


def test_reindex_upgrades_the_search_tokenizer(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()
    with connect(vault.db_path) as connection:
        connection.execute("DROP TABLE docs_fts")
        connection.execute("CREATE VIRTUAL TABLE docs_fts USING fts5(path, title, body)")
    ingest(vault, FIXTURES / "note.md", min_chars=0)
    assert vault.search("telescopes") == []
    assert search_index_needs_rebuild(vault.db_path)

    assert reindex(vault.path) == (1, 0, 0)

    assert vault.search("telescopes")
    assert not search_index_needs_rebuild(vault.db_path)
