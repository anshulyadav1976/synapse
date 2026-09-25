import pytest

from synapse import Vault
from synapse.index import reindex
from synapse.notes import approve_note, list_proposals, propose_note, read_note


def test_agent_note_requires_review_and_survives_reindex(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()

    proposed = propose_note(
        vault,
        "launch-decision",
        "Launch decision",
        "Use the small local-first release.",
        "User decision in project discussion",
        "discussion:launch:v1",
    )
    assert proposed["status"] == "pending"
    assert "+Use the small local-first release." in proposed["diff"]
    assert not (vault.notes_path / "launch-decision.md").exists()
    assert len(list_proposals(vault)) == 1

    committed = approve_note(vault, proposed["proposal_id"])
    assert committed["status"] == "committed"
    assert vault.search("local-first")[0]["path"] == "notes/launch-decision.md"

    vault.db_path.unlink()
    assert reindex(vault.path) == (0, 0, 1)
    assert vault.search("local-first")


def test_note_proposals_are_idempotent_and_revision_checked(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()
    first = propose_note(vault, "project", "Project", "First fact.", "User", "project:1")
    assert propose_note(vault, "project", "Project", "First fact.", "User", "project:1") == first
    approve_note(vault, first["proposal_id"])

    note = read_note(vault, "project")
    second = propose_note(
        vault,
        "project",
        "Project",
        "Second fact.",
        "User",
        "project:2",
        note["revision"],
    )
    approve_note(vault, second["proposal_id"])
    assert "First fact." in read_note(vault, "project")["markdown"]
    assert "Second fact." in read_note(vault, "project")["markdown"]

    with pytest.raises(ValueError, match="stale"):
        propose_note(vault, "project", "Project", "Stale fact.", "User", "project:3", note["revision"])


def test_idempotency_key_cannot_be_reused_for_different_content(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()
    propose_note(vault, "alpha", "Alpha", "One.", "User", "same-key")
    with pytest.raises(ValueError, match="different proposal"):
        propose_note(vault, "alpha", "Alpha", "Two.", "User", "same-key")
