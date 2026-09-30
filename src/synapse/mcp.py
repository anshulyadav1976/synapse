"""A small stdio MCP server with no SDK dependency."""

import json
import sys
from pathlib import PurePosixPath
from typing import Any

from .graph import neighbors
from .notes import propose_note, read_note
from .server import _safe_source
from .vault import Vault

LATEST_PROTOCOL = "2025-06-18"

TOOLS = [
    {
        "name": "search",
        "description": "Search the vault index. Use hybrid=true for conceptual wording or after a keyword miss; it requires a prior `synapse embed`. Results say whether to open them with read_page, read_note, or read_source. Prefer one synthesized page when available.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Words to search for"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                "hybrid": {
                    "type": "boolean",
                    "default": False,
                    "description": "Fuse keyword and semantic results; may call the configured embedding endpoint",
                },
                "after": {"type": "string", "description": "ISO date lower bound for raw sources"},
                "before": {"type": "string", "description": "ISO date upper bound for raw sources"},
                "source": {"type": "string", "description": "Raw adapter name, such as chatgpt"},
                "kind": {"type": "string", "enum": ["raw", "wiki", "note"]},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_page",
        "description": "Read one wiki page returned by search or list_pages. Do not bulk-read pages.",
        "inputSchema": {
            "type": "object",
            "properties": {"slug": {"type": "string"}},
            "required": ["slug"],
        },
    },
    {
        "name": "read_note",
        "description": "Read one approved agent note and its revision. Use the revision as parent_revision when proposing an append.",
        "inputSchema": {
            "type": "object",
            "properties": {"note_id": {"type": "string"}},
            "required": ["note_id"],
        },
    },
    {
        "name": "list_pages",
        "description": "List page slugs and titles only. Read one relevant page at a time afterward.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "neighbors",
        "description": "List pages directly connected to one page. Read only a relevant neighbor.",
        "inputSchema": {
            "type": "object",
            "properties": {"slug": {"type": "string"}},
            "required": ["slug"],
        },
    },
    {
        "name": "read_source",
        "description": "Read one immutable raw source cited by a page when provenance is necessary.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "propose_note",
        "description": "Propose one durable semantic note for human approval. This never edits raw history or commits the note. Do not use it for credentials, tokens, browser/session/workspace state, transient tool output, or routine conversation turns.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "string", "description": "Stable lowercase slug"},
                "title": {"type": "string"},
                "body": {"type": "string", "description": "One durable fact or decision"},
                "provenance": {"type": "string", "description": "Human-readable source or reason"},
                "idempotency_key": {"type": "string", "description": "Stable key for this exact proposal"},
                "parent_revision": {
                    "type": "string",
                    "description": "Revision from read_note; omit only for a new note",
                },
            },
            "required": ["note_id", "title", "body", "provenance", "idempotency_key"],
        },
    },
]


def _text(value: object, error: bool = False) -> dict[str, object]:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": text}], "isError": error}


def _string(arguments: dict[str, Any], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def call_tool(vault: Vault, name: str, arguments: dict[str, Any]) -> dict[str, object]:
    if name == "search":
        limit = int(arguments.get("limit", 5))
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")
        results = vault.search(
            _string(arguments, "query"),
            limit,
            hybrid=bool(arguments.get("hybrid", False)),
            after=arguments.get("after") if isinstance(arguments.get("after"), str) else None,
            before=arguments.get("before")
            if isinstance(arguments.get("before"), str)
            else None,
            source=arguments.get("source")
            if isinstance(arguments.get("source"), str)
            else None,
            kind=arguments.get("kind") if isinstance(arguments.get("kind"), str) else None,
        )
        for result in results:
            path = PurePosixPath(result["path"])
            if path.parts[0] == "wiki":
                result.update(kind="page", slug=path.stem)
            elif path.parts[0] == "notes":
                result.update(kind="note", note_id=path.stem)
            else:
                result.update(kind="source", source_path=path.as_posix())
        return _text(results)
    if name == "read_page":
        slug = _string(arguments, "slug")
        if "/" in slug or ".." in slug:
            raise ValueError("slug must name one wiki page")
        path = vault.wiki_path / f"{slug}.md"
        if not path.is_file() or path.name.startswith("."):
            raise FileNotFoundError(f"Page not found: {slug}")
        return _text(path.read_text(encoding="utf-8"))
    if name == "read_note":
        return _text(read_note(vault, _string(arguments, "note_id")))
    if name == "list_pages":
        pages = []
        for path in sorted(vault.wiki_path.glob("*.md")):
            if path.name.startswith("."):
                continue
            heading = path.read_text(encoding="utf-8").splitlines()[0].removeprefix("# ")
            pages.append({"slug": path.stem, "title": heading})
        return _text(pages)
    if name == "neighbors":
        return _text(neighbors(vault, _string(arguments, "slug")))
    if name == "read_source":
        relative: PurePosixPath = _safe_source(_string(arguments, "path"))
        path = vault.path / relative
        if not path.is_file():
            raise FileNotFoundError(f"Source not found: {relative}")
        return _text(path.read_text(encoding="utf-8"))
    if name == "propose_note":
        parent = arguments.get("parent_revision")
        if parent is not None and not isinstance(parent, str):
            raise ValueError("parent_revision must be a string")
        return _text(
            propose_note(
                vault,
                _string(arguments, "note_id"),
                _string(arguments, "title"),
                _string(arguments, "body"),
                _string(arguments, "provenance"),
                _string(arguments, "idempotency_key"),
                parent,
            )
        )
    raise ValueError(f"Unknown tool: {name}")


def dispatch(vault: Vault, message: dict[str, Any]) -> dict[str, object] | None:
    request_id = message.get("id")
    method = message.get("method")
    if request_id is None:
        return None
    try:
        if method == "initialize":
            requested = (message.get("params") or {}).get("protocolVersion")
            result: object = {
                "protocolVersion": requested if isinstance(requested, str) else LATEST_PROTOCOL,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "synapse", "version": "0.2.0"},
                "instructions": "Search first and read one relevant item at a time. Only propose durable semantic notes; a human approves them outside MCP.",
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = message.get("params") or {}
            try:
                result = call_tool(vault, str(params.get("name", "")), params.get("arguments") or {})
            except (ValueError, FileNotFoundError) as error:
                result = _text(str(error), True)
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except (TypeError, ValueError) as error:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32602, "message": str(error)},
        }


def serve(vault: Vault) -> None:
    for line in sys.stdin:
        try:
            message = json.loads(line)
            response = dispatch(vault, message)
        except json.JSONDecodeError as error:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {error.msg}"},
            }
        if response is not None:
            print(json.dumps(response, ensure_ascii=False, separators=(",", ":")), flush=True)
