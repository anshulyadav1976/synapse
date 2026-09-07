from synapse import Vault
from synapse.db import connect
from synapse.index import index_document
from synapse.query import ask


def test_ask_retrieves_pages_and_injects_no_corpus_elsewhere(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()
    body = "# Community Garden\n\nThe owner grows basil.\n"
    path = vault.wiki_path / "community-garden.md"
    path.write_text(body)
    with connect(vault.db_path) as connection:
        index_document(connection, "wiki/community-garden.md", "Community Garden", body)
    calls = []

    def fake_complete(system, user):
        calls.append((system, user))
        return "The owner grows basil [[community-garden]]."

    result = ask(vault, "What grows in the garden?", fake_complete)
    assert result.pages == ["community-garden"]
    assert result.answer.endswith("[[community-garden]].")
    assert len(calls) == 1
    assert body not in calls[0][0]
    assert body in calls[0][1]


def test_retrieval_ignores_common_words(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()
    relevant = "# Graph Project\n\nWon a synthetic graph hackathon.\n"
    noise = "# Other\n\nWhat I did in the unrelated test.\n"
    with connect(vault.db_path) as connection:
        for slug, body in (("graph-project", relevant), ("other", noise)):
            path = vault.wiki_path / f"{slug}.md"
            path.write_text(body)
            index_document(connection, f"wiki/{slug}.md", slug, body)
    pages = ask(
        vault,
        "What did I do in the graph hackathon?",
        lambda _system, user: user,
    ).pages
    assert pages[0] == "graph-project"
