from synapse import Vault
from synapse.db import connect
from synapse.index import index_document, index_item
from synapse.models import Item
from synapse.semantic import build_embeddings, estimate_embeddings


def _vectors(texts):
    return [
        [1.0, 0.0] if "headroom" in text.casefold() or "rapid growth" in text.casefold() else [0.0, 1.0]
        for text in texts
    ]


def test_hybrid_search_finds_a_paraphrase_and_updates_incrementally(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()
    pages = {
        "capacity.md": "# Capacity plan\n\nIncrease server headroom before demand peaks.\n",
        "lunch.md": "# Team lunch\n\nBook the Italian restaurant for Friday.\n",
    }
    with connect(vault.db_path) as connection:
        for name, body in pages.items():
            (vault.wiki_path / name).write_text(body)
            index_document(connection, f"wiki/{name}", body.splitlines()[0][2:], body)

    first = build_embeddings(
        vault.path, vault.db_path, "text-embedding-3-small", _vectors
    )
    second = build_embeddings(
        vault.path, vault.db_path, "text-embedding-3-small", _vectors
    )

    assert first.embedded_chunks == 2
    assert second.embedded_chunks == 0
    assert vault.search("How do we handle rapid growth?") == []
    result = vault.search(
        "How do we handle rapid growth?",
        hybrid=True,
        embed=_vectors,
    )[0]
    assert result["path"] == "wiki/capacity.md"
    assert result["match"] == "semantic"

    updated = "# Capacity plan\n\nIncrease server headroom before the launch.\n"
    (vault.wiki_path / "capacity.md").write_text(updated)
    with connect(vault.db_path) as connection:
        index_document(connection, "wiki/capacity.md", "Capacity plan", updated)
    estimate = estimate_embeddings(
        vault.path, vault.db_path, "text-embedding-3-small"
    )
    assert estimate.pending_chunks == 1


def test_search_filters_dated_raw_sources(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()
    with connect(vault.db_path) as connection:
        index_item(
            connection,
            Item("old", "chatgpt", "Plan", "2025-01-01T00:00:00+00:00", text="launch"),
            "raw/chatgpt/2025-01/old.md",
            "Launch plan",
        )
        index_item(
            connection,
            Item("new", "claude", "Plan", "2026-09-01T00:00:00+00:00", text="launch"),
            "raw/claude/2026-09/new.md",
            "Launch plan",
        )

    results = vault.search("launch", after="2026-01-01", source="claude", kind="raw")

    assert [result["path"] for result in results] == ["raw/claude/2026-09/new.md"]
