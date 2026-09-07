import sqlite3

from synapse import Vault


def test_init_creates_complete_empty_vault(tmp_path):
    vault = Vault(tmp_path / "brain")
    vault.init()

    assert vault.raw_path.is_dir()
    assert vault.wiki_path.is_dir()
    assert vault.config_path.read_text().startswith("# Synapse")
    assert vault.status() == {"items": 0, "unbuilt": 0, "pages": 0, "sources": {}}

    with sqlite3.connect(vault.db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            )
        }
    assert {"items", "docs_fts", "links"} <= tables

