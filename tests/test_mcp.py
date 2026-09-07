import json

from synapse import Vault
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
    listed = dispatch(vault, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert listed["result"]["tools"] == TOOLS
    assert {tool["name"] for tool in TOOLS} == {
        "search",
        "read_page",
        "list_pages",
        "neighbors",
        "read_source",
    }


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
