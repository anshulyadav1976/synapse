import json

from synapse import Vault, __version__
from synapse.mcp import TOOLS, call_tool, dispatch
from synapse.server import demo_vault


def test_initialize_and_tools_list(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()
    initialized = dispatch(
        vault,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        },
    )
    assert initialized["result"]["protocolVersion"] == "2025-06-18"
    assert initialized["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert initialized["result"]["serverInfo"]["version"] == __version__
    listed = dispatch(vault, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert listed["result"]["tools"] == TOOLS
    assert {tool["name"] for tool in TOOLS} == {
        "search",
        "read_page",
        "read_note",
        "list_pages",
        "neighbors",
        "read_source",
        "propose_note",
    }


def test_tool_metadata_describes_parameters_and_side_effects():
    for tool in TOOLS:
        assert all(field.get("description") for field in tool["inputSchema"]["properties"].values())
        annotations = tool["annotations"]
        assert annotations["readOnlyHint"] == (tool["name"] != "propose_note")
        assert annotations["openWorldHint"] == (tool["name"] == "search")
        # Output schemas require structuredContent; these tools deliberately retain text.
        assert "outputSchema" not in tool
    proposal = next(tool for tool in TOOLS if tool["name"] == "propose_note")
    assert proposal["annotations"]["idempotentHint"] is True
    assert proposal["annotations"]["destructiveHint"] is False


def test_catalog_and_neighbors_match_documented_shapes():
    vault, temporary = demo_vault()
    try:
        pages = json.loads(call_tool(vault, "list_pages", {})["content"][0]["text"])
        assert len(pages) == 20
        assert pages == sorted(pages, key=lambda page: page["slug"])
        assert all(set(page) == {"slug", "title"} for page in pages)
        for page in pages:
            links = json.loads(
                call_tool(vault, "neighbors", {"slug": page["slug"]})["content"][0]["text"]
            )
            assert links == sorted(links, key=lambda link: link["slug"])
            assert all(set(link) == {"slug", "direction", "phrase"} for link in links)
            assert all(link["direction"] in {"in", "out"} for link in links)
        missing = call_tool(vault, "neighbors", {"slug": "nonexistent-synthetic-page"})
        assert json.loads(missing["content"][0]["text"]) == []
    finally:
        temporary.cleanup()


def test_demo_tool_sequence_reads_one_page_and_source():
    vault, temporary = demo_vault()
    try:
        searched = call_tool(vault, "search", {"query": "solar irrigation", "limit": 5})
        results = json.loads(searched["content"][0]["text"])
        page_result = next(result for result in results if result["path"].startswith("wiki/"))
        assert page_result["kind"] == "page"
        page = call_tool(vault, "read_page", {"slug": page_result["slug"]})
        assert "solar" in page["content"][0]["text"].casefold()
        source_result = next(result for result in results if result["path"].startswith("raw/"))
        assert source_result["kind"] == "source"
        assert source_result["source_path"] == source_result["path"]
        source = call_tool(
            vault,
            "read_source",
            {"path": "raw/demo/2026-04/garden-log.md"},
        )
        assert "irrigation" in source["content"][0]["text"].casefold()
    finally:
        temporary.cleanup()


def test_tool_errors_are_visible_to_the_model(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()
    response = dispatch(
        vault,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "read_page", "arguments": {"slug": "missing"}},
        },
    )
    assert response["result"]["isError"] is True

    hybrid = dispatch(
        vault,
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "search",
                "arguments": {"query": "conceptual match", "hybrid": True},
            },
        },
    )
    assert hybrid["result"]["isError"] is True


def test_agent_can_propose_but_not_commit_a_note(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()
    response = call_tool(
        vault,
        "propose_note",
        {
            "note_id": "release-choice",
            "title": "Release choice",
            "body": "Ship the local-first version.",
            "provenance": "Explicit user decision",
            "idempotency_key": "release-choice:1",
        },
    )
    proposal = json.loads(response["content"][0]["text"])
    assert proposal["status"] == "pending"
    assert not (vault.notes_path / "release-choice.md").exists()
    assert "approve-note" not in {tool["name"] for tool in TOOLS}
