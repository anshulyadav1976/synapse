"""Human-approved, append-only notes proposed by agents."""

import difflib
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .build import valid_slug
from .db import connect
from .index import index_document
from .vault import Vault

KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
PROPOSAL_ID = re.compile(r"^[a-f0-9]{16}$")


def revision(markdown: str) -> str:
    return hashlib.sha256(markdown.encode()).hexdigest()


def _clean(value: str, name: str, limit: int, multiline: bool = False) -> str:
    value = value.strip()
    if not value or len(value) > limit or "\x00" in value:
        raise ValueError(f"{name} must contain 1 to {limit} safe characters")
    if not multiline and ("\n" in value or "\r" in value):
        raise ValueError(f"{name} must fit on one line")
    return value


def _proposal_path(vault: Vault, proposal_id: str) -> Path:
    if not PROPOSAL_ID.fullmatch(proposal_id):
        raise ValueError("proposal_id must be the 16-character ID returned by propose_note")
    return vault.proposals_path / f"{proposal_id}.json"


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Proposal not found: {path.stem}")
    return json.loads(path.read_text(encoding="utf-8"))


def read_note(vault: Vault, note_id: str) -> dict[str, str]:
    if not valid_slug(note_id):
        raise ValueError("note_id must be a lowercase slug")
    path = vault.notes_path / f"{note_id}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Note not found: {note_id}")
    markdown = path.read_text(encoding="utf-8")
    return {"note_id": note_id, "revision": revision(markdown), "markdown": markdown}


def propose_note(
    vault: Vault,
    note_id: str,
    title: str,
    body: str,
    provenance: str,
    idempotency_key: str,
    parent_revision: str | None = None,
) -> dict[str, object]:
    if not valid_slug(note_id):
        raise ValueError("note_id must be a lowercase slug")
    title = _clean(title, "title", 200)
    body = _clean(body, "body", 12_000, multiline=True)
    provenance = _clean(provenance, "provenance", 500)
    if not KEY.fullmatch(idempotency_key):
        raise ValueError("idempotency_key must use 1-128 letters, numbers, '.', '_', ':', or '-'")
    if parent_revision is not None and not re.fullmatch(r"[a-f0-9]{64}", parent_revision):
        raise ValueError("parent_revision must be the revision returned by read_note")

    proposal_id = hashlib.sha256(idempotency_key.encode()).hexdigest()[:16]
    proposal_path = _proposal_path(vault, proposal_id)
    request = {
        "note_id": note_id,
        "title": title,
        "body": body,
        "provenance": provenance,
        "idempotency_key": idempotency_key,
        "parent_revision": parent_revision,
    }
    if proposal_path.exists():
        existing = _load(proposal_path)
        if existing["request"] != request:
            raise ValueError("idempotency_key was already used for a different proposal")
        return _public(existing)

    note_path = vault.notes_path / f"{note_id}.md"
    current = note_path.read_text(encoding="utf-8") if note_path.exists() else ""
    base_revision = revision(current) if current else None
    if current:
        current_title = current.splitlines()[0].removeprefix("# ").strip()
        if title != current_title:
            raise ValueError(f"title must remain {current_title!r} for existing note {note_id}")
        if parent_revision != base_revision:
            raise ValueError("parent_revision is stale; call read_note and propose again")
    elif parent_revision is not None:
        raise ValueError("parent_revision must be omitted for a new note")

    created_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    entry = (
        f"### {created_at}\n\n{body}\n\n"
        f"_Source: {provenance} · Idempotency: `{idempotency_key}`_\n"
    )
    proposed = (
        current.rstrip() + "\n\n" + entry
        if current
        else f"# {title}\n\n## Agent notes\n\n{entry}"
    )
    diff = "".join(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile=f"notes/{note_id}.md",
            tofile=f"notes/{note_id}.md (proposed)",
        )
    )
    proposal: dict[str, object] = {
        "proposal_id": proposal_id,
        "status": "pending",
        "created_at": created_at,
        "base_revision": base_revision,
        "proposed_revision": revision(proposed),
        "request": request,
        "proposed_markdown": proposed,
        "diff": diff,
    }
    vault.proposals_path.mkdir(parents=True, exist_ok=True)
    proposal_path.write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return _public(proposal)


def _public(proposal: dict[str, Any]) -> dict[str, object]:
    request = proposal["request"]
    return {
        "proposal_id": proposal["proposal_id"],
        "status": proposal["status"],
        "note_id": request["note_id"],
        "title": request["title"],
        "base_revision": proposal["base_revision"],
        "proposed_revision": proposal["proposed_revision"],
        "diff": proposal["diff"],
        "next": f"Review with `synapse proposals {proposal['proposal_id']}` and approve with `synapse approve-note {proposal['proposal_id']}`.",
    }


def list_proposals(vault: Vault) -> list[dict[str, object]]:
    if not vault.proposals_path.exists():
        return []
    proposals = [_load(path) for path in sorted(vault.proposals_path.glob("*.json"))]
    return [_public(proposal) for proposal in proposals if proposal["status"] == "pending"]


def get_proposal(vault: Vault, proposal_id: str) -> dict[str, object]:
    return _public(_load(_proposal_path(vault, proposal_id)))


def approve_note(vault: Vault, proposal_id: str) -> dict[str, str]:
    proposal_path = _proposal_path(vault, proposal_id)
    proposal = _load(proposal_path)
    request = proposal["request"]
    note_id = request["note_id"]
    note_path = vault.notes_path / f"{note_id}.md"
    if proposal["status"] == "committed":
        return {"note_id": note_id, "revision": proposal["proposed_revision"], "status": "committed"}

    current = note_path.read_text(encoding="utf-8") if note_path.exists() else ""
    current_revision = revision(current) if current else None
    if current_revision != proposal["base_revision"]:
        raise ValueError("Note changed after this proposal; ask the agent to propose it again")

    vault.notes_path.mkdir(parents=True, exist_ok=True)
    note_path.write_text(proposal["proposed_markdown"], encoding="utf-8")
    with connect(vault.db_path) as connection:
        index_document(
            connection,
            f"notes/{note_id}.md",
            request["title"],
            proposal["proposed_markdown"],
        )
    proposal["status"] = "committed"
    proposal["committed_at"] = datetime.now(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    proposal_path.write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"note_id": note_id, "revision": proposal["proposed_revision"], "status": "committed"}
