from synapse import Vault
from synapse.db import connect
from synapse.index import index_document, index_item
from synapse.models import Item


def test_search_stems_questions_and_falls_back_to_partial_matches(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()
    with connect(vault.db_path) as connection:
        index_document(
            connection,
            "wiki/audit.md",
            "Vendor audit",
            "A shipment failed the compliance audit.",
        )
        index_document(
            connection,
            "wiki/directory.md",
            "Vendor directory",
            "Current supplier contacts.",
        )

    results = vault.search("Which vendors failed their audits?", 2)

    assert [result["path"] for result in results] == [
        "wiki/audit.md",
        "wiki/directory.md",
    ]


def test_search_keeps_meaningful_short_terms_and_boosts_recent_sources(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()
    with connect(vault.db_path) as connection:
        index_item(
            connection,
            Item("old", "test", "US plan", "2025-01-01T00:00:00+00:00", text="US launch"),
            "raw/test/2025-01/old.md",
            "US launch plan",
        )
        index_item(
            connection,
            Item("new", "test", "US plan", "2026-01-01T00:00:00+00:00", text="US launch"),
            "raw/test/2026-01/new.md",
            "US launch plan",
        )

    results = vault.search("US launch")

    assert [result["path"] for result in results[:2]] == [
        "raw/test/2026-01/new.md",
        "raw/test/2025-01/old.md",
    ]
    assert results[0]["date"] == "2026-01-01"
