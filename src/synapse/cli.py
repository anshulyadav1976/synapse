"""Command-line entry point."""

import argparse
import json
import os
import time

from .build import actual_cost, build, estimate
from .graph import graph_json, neighbors
from .index import reindex
from .ingest import ingest
from .llm import OpenAICompatible
from .mcp import serve as serve_mcp
from .query import ask
from .server import demo_vault, serve
from .vault import Vault

DEFAULT_VAULT = os.environ.get("SYNAPSE_VAULT", "./synapse-vault")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="synapse")
    commands = root.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="create a Synapse vault")
    init.add_argument("path", nargs="?", default=DEFAULT_VAULT)

    status = commands.add_parser("status", help="show vault counts")
    status.add_argument("--vault", default=DEFAULT_VAULT)

    ingest_command = commands.add_parser("ingest", help="import text without API calls")
    ingest_command.add_argument("input")
    ingest_command.add_argument("--vault", default=DEFAULT_VAULT)
    ingest_command.add_argument("--format", dest="format_name")
    ingest_command.add_argument("--min-chars", type=int, default=200)

    search = commands.add_parser("search", help="full-text search the vault")
    search.add_argument("query")
    search.add_argument("--vault", default=DEFAULT_VAULT)
    search.add_argument("--limit", type=int, default=10)

    rebuild = commands.add_parser("reindex", help="rebuild SQLite from Markdown")
    rebuild.add_argument("--vault", default=DEFAULT_VAULT)

    build_command = commands.add_parser("build", help="turn unbuilt sources into wiki pages")
    build_command.add_argument("--vault", default=DEFAULT_VAULT)
    build_command.add_argument("--limit", type=int)
    build_command.add_argument("--dry-run", action="store_true")
    build_command.add_argument("--oldest", action="store_true")
    build_command.add_argument("--yes", action="store_true", help="confirm a large estimated spend")

    graph_command = commands.add_parser("graph", help="export the wiki graph")
    graph_command.add_argument("--vault", default=DEFAULT_VAULT)
    graph_command.add_argument("--json", action="store_true", required=True)

    neighbor_command = commands.add_parser("neighbors", help="list a page's graph neighbors")
    neighbor_command.add_argument("slug")
    neighbor_command.add_argument("--vault", default=DEFAULT_VAULT)

    ask_command = commands.add_parser("ask", help="answer from retrieved wiki pages")
    ask_command.add_argument("question")
    ask_command.add_argument("--vault", default=DEFAULT_VAULT)
    ask_command.add_argument("--limit", type=int, default=5)

    serve_command = commands.add_parser("serve", help="open the local dashboard")
    serve_command.add_argument("--vault", default=DEFAULT_VAULT)
    serve_command.add_argument("--demo", action="store_true")
    serve_command.add_argument("--port", type=int, default=8765)
    serve_command.add_argument("--no-open", action="store_true")

    mcp_command = commands.add_parser("mcp", help="run the stdio MCP server")
    mcp_command.add_argument("--vault", default=DEFAULT_VAULT)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "init":
        vault = Vault(args.path)
        vault.init()
        print(f"Initialized Synapse vault at {vault.path}")
        return 0

    vault = Vault(args.vault)
    if args.command == "status":
        summary = vault.status()
        print(f"Vault: {vault.path}")
        print(f"Items: {summary['items']}")
        print(f"Unbuilt: {summary['unbuilt']}")
        print(f"Pages: {summary['pages']}")
        sources = summary["sources"]
        source_text = ", ".join(f"{name}={count}" for name, count in sources.items())
        print("Sources: " + (source_text or "none"))
        return 0
    if args.command == "ingest":
        started = time.perf_counter()
        result = ingest(
            vault,
            args.input,
            args.format_name,
            args.min_chars,
            vault.config().owner,
        )
        label = "Conversations" if result.format == "chatgpt" else "Items"
        print(f"Format: {result.format}")
        print(f"{label} seen: {result.seen}")
        print(f"Items added: {result.added}")
        print(f"Items skipped: {result.skipped + result.filtered}")
        print(f"  Already present: {result.skipped}")
        print(f"  Below --min-chars: {result.filtered}")
        print(f"Wall time: {time.perf_counter() - started:.2f}s")
        print("API calls: 0")
        return 0
    if args.command == "search":
        results = vault.search(args.query, args.limit)
        for result in results:
            print(f"{result['title']}  ({result['path']})")
            print(f"  {result['snippet']}")
        print(f"{len(results)} result(s)")
        return 0
    if args.command == "reindex":
        raw_count, page_count = reindex(vault.path)
        print(f"Reindexed {raw_count} raw item(s) and {page_count} wiki page(s)")
        return 0
    if args.command == "graph":
        print(json.dumps(graph_json(vault), ensure_ascii=False, indent=2))
        return 0
    if args.command == "neighbors":
        for neighbor in neighbors(vault, args.slug):
            print(f"{neighbor['slug']}\t{neighbor['direction']}\t{neighbor['phrase']}")
        return 0
    if args.command == "ask":
        config = vault.config()
        client = OpenAICompatible(config.base_url, config.api_key, config.model)
        result = ask(vault, args.question, client.complete, args.limit)
        print(result.answer)
        print("\nRetrieved pages: " + ", ".join(f"[[{slug}]]" for slug in result.pages))
        cost = actual_cost(config, client.usage.input_tokens, client.usage.output_tokens)
        print(f"Actual cost: ${cost:.4f}")
        return 0
    if args.command == "serve":
        temporary = None
        if args.demo:
            vault, temporary = demo_vault()
        serve(vault, args.port, not args.no_open)
        if temporary:
            temporary.cleanup()
        return 0
    if args.command == "mcp":
        serve_mcp(vault)
        return 0

    config = vault.config()
    quote = estimate(vault, config, args.limit, args.oldest)
    print(f"Model: {config.model}")
    print(f"Items: {quote.items}")
    print(f"Estimated input tokens: {quote.input_tokens}")
    print(f"Estimated output tokens: {quote.output_tokens}")
    print(f"Estimated cost: ${quote.dollars:.4f}")
    if args.dry_run or quote.items == 0:
        print("API calls: 0")
        return 0
    if quote.input_tokens > 200_000 and not args.yes:
        answer = input("Estimate exceeds 200,000 input tokens. Type 'yes' to continue: ")
        if answer.strip().casefold() != "yes":
            print("Build cancelled; API calls: 0")
            return 1
    if not config.api_key and not config.base_url.startswith(
        ("http://localhost", "http://127.0.0.1")
    ):
        raise RuntimeError(
            "No API key configured. Set SYNAPSE_API_KEY or add api_key to synapse.toml."
        )
    client = OpenAICompatible(config.base_url, config.api_key, config.model)
    result = build(vault, config, client.complete, args.limit, args.oldest)
    print(f"Built items: {result.items}")
    print(f"Pages written: {result.pages}")
    print(f"Actual input tokens: {client.usage.input_tokens}")
    print(f"Actual output tokens: {client.usage.output_tokens}")
    cost = actual_cost(config, client.usage.input_tokens, client.usage.output_tokens)
    print(f"Actual cost: ${cost:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
