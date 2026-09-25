import time

import pytest

from synapse import Vault
from synapse.notes import approve_note, propose_note
from synapse.server import Dashboard, _safe_source, demo_vault


def test_demo_vault_is_populated_and_disposable():
    vault, temporary = demo_vault()
    try:
        status = vault.status()
        graph = Dashboard(vault).get("/api/graph", {})
        assert status["items"] == 5
        assert status["pages"] == 20
        assert len(graph["nodes"]) == 20
        assert len(graph["edges"]) >= 20
    finally:
        temporary.cleanup()


def test_dashboard_reads_and_edits_a_page(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()
    page = vault.wiki_path / "alpha.md"
    page.write_text("# Alpha\n")
    dashboard = Dashboard(vault)
    assert dashboard.get("/api/page", {"slug": ["alpha"]})["markdown"] == "# Alpha\n"
    dashboard.write_page({"slug": "alpha", "markdown": "# Alpha\n\n- [[beta]] — link"})
    assert "[[beta]]" in page.read_text()


def test_dashboard_reads_an_approved_agent_note(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()
    proposal = propose_note(vault, "choice", "Choice", "Keep it small.", "User", "choice:1")
    approve_note(vault, proposal["proposal_id"])
    note = Dashboard(vault).get("/api/note", {"note_id": ["choice"]})
    assert note["note_id"] == "choice"
    assert "Keep it small." in note["markdown"]


def test_source_paths_cannot_escape_raw():
    assert _safe_source("raw/demo/2026-01/note.md").parts[0] == "raw"
    with pytest.raises(ValueError):
        _safe_source("../synapse.toml")
    with pytest.raises(ValueError):
        _safe_source("wiki/page.md")


def test_ingest_job_reports_live_progress(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()
    note = tmp_path / "note.txt"
    note.write_text("A synthetic note for the background ingest job.")
    dashboard = Dashboard(vault)
    job_id = dashboard.start_ingest({"path": str(note)})["job_id"]
    deadline = time.monotonic() + 2
    while dashboard.jobs[job_id]["state"] == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert dashboard.jobs[job_id]["state"] == "complete"
    assert dashboard.jobs[job_id]["result"]["added"] == 1
