"""Command-line entry point."""

import argparse
import json
import os
import time

from .build import actual_cost, build, estimate
from .db import initialize, search_index_needs_rebuild
from .graph import graph_json, neighbors
from .index import reindex
from .ingest import ingest
from .llm import OpenAICompatible
from .mcp import serve as serve_mcp
from .notes import approve_note, get_proposal, list_proposals
from .query import ask
from .semantic import build_embeddings, estimate_embeddings
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
    search.add_argument("--hybrid", action="store_true", help="fuse FTS with semantic search")
    search.add_argument("--after", help="only dated raw sources on or after this ISO date")
    search.add_argument("--before", help="only dated raw sources before this ISO date")
    search.add_argument("--source", help="only one raw source adapter, such as chatgpt")
    search.add_argument("--kind", choices=("raw", "wiki", "note"))

    rebuild = commands.add_parser("reindex", help="rebuild SQLite from Markdown")
    rebuild.add_argument("--vault", default=DEFAULT_VAULT)

    embed_command = commands.add_parser("embed", help="build the optional semantic index")
    embed_command.add_argument("--vault", default=DEFAULT_VAULT)
    embed_command.add_argument("--include-raw", action="store_true")
    embed_command.add_argument("--dry-run", action="store_true")
    embed_command.add_argument("--yes", action="store_true", help="confirm a large embedding run")

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

    proposals = commands.add_parser("proposals", help="list or review pending agent notes")
    proposals.add_argument("proposal_id", nargs="?")
    proposals.add_argument("--vault", default=DEFAULT_VAULT)

    approve = commands.add_parser("approve-note", help="approve one proposed agent note")
    approve.add_argument("proposal_id")
    approve.add_argument("--vault", default=DEFAULT_VAULT)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "init":
        vault = Vault(args.path)
        vault.init()
        print(f"Initialized Synapse vault at {vault.path}")
        return 0

    vault = Vault(args.vault)
    if vault.db_path.exists():
        initialize(vault.db_path)
    if args.command == "status":
        summary = vault.status()
        print(f"Vault: {vault.path}")
        print(f"Items: {summary['items']}")
        print(f"Unbuilt: {summary['unbuilt']}")
        print(f"Pages: {summary['pages']}")
        print(f"Agent notes: {summary['notes']}")
        print(f"Pending proposals: {summary['proposals']}")
        models = ", ".join(summary["semantic_models"])
        print(f"Semantic chunks: {summary['semantic_chunks']}" + (f" ({models})" if models else ""))
        sources = summary["sources"]
        source_text = ", ".join(f"{name}={count}" for name, count in sources.items())
        print("Sources: " + (source_text or "none"))
        if search_index_needs_rebuild(vault.db_path):
            print(f'Search index: outdated tokenizer; run: synapse reindex --vault "{vault.path}"')
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
        label = "Conversations" if result.format in {"chatgpt", "claude"} else "Items"
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
        results = vault.search(
            args.query,
            args.limit,
            hybrid=args.hybrid,
            after=args.after,
            before=args.before,
            source=args.source,
            kind=args.kind,
        )
        for result in results:
            match = f" [{result['match']}]" if result.get("match") else ""
            print(f"{result['title']}  ({result['path']}){match}")
            print(f"  {result['snippet']}")
        print(f"{len(results)} result(s)")
        return 0
    if args.command == "reindex":
        raw_count, page_count, note_count = reindex(vault.path)
        print(
            f"Reindexed {raw_count} raw item(s), {page_count} wiki page(s), "
            f"and {note_count} agent note(s)"
        )
        return 0
    if args.command == "embed":
        if not vault.db_path.exists():
            raise FileNotFoundError(f"No Synapse vault found at {vault.path}. Run: synapse init")
        initialize(vault.db_path)
        config = vault.config()
        quote = estimate_embeddings(
            vault.path,
            vault.db_path,
            config.embedding_model,
            args.include_raw,
        )
        print(f"Embedding model: {config.embedding_model}")
        print(f"Documents: {quote.documents}")
        print(f"Chunks: {quote.chunks}")
        print(f"Chunks to embed: {quote.pending_chunks}")
        print(f"Estimated input tokens: {quote.input_tokens}")
        if args.dry_run or quote.pending_chunks == 0:
            print("API calls: 0")
            return 0
        if quote.input_tokens > 200_000 and not args.yes:
            answer = input("Estimate exceeds 200,000 input tokens. Type 'yes' to continue: ")
            if answer.strip().casefold() != "yes":
                print("Embedding cancelled; API calls: 0")
                return 1
        if not config.embedding_api_key and not config.embedding_base_url.startswith(
            ("http://localhost", "http://127.0.0.1")
        ):
            raise RuntimeError(
                "No embedding API key configured. Set SYNAPSE_EMBEDDING_API_KEY "
                "or SYNAPSE_API_KEY."
            )
        client = OpenAICompatible(
            config.embedding_base_url,
            config.embedding_api_key,
            config.embedding_model,
        )
        result = build_embeddings(
            vault.path,
            vault.db_path,
            config.embedding_model,
            client.embed,
            args.include_raw,
        )
        print(f"Embedded chunks: {result.embedded_chunks}")
        print(f"Unchanged chunks: {result.skipped_chunks}")
        print(f"Actual input tokens: {client.usage.input_tokens}")
        return 0
    if args.command == "proposals":
        if args.proposal_id:
            proposal = get_proposal(vault, args.proposal_id)
            print(f"Proposal: {proposal['proposal_id']} ({proposal['status']})")
            print(f"Note: {proposal['note_id']} — {proposal['title']}")
            print(proposal["diff"], end="")
        else:
            proposals = list_proposals(vault)
            for proposal in proposals:
                print(f"{proposal['proposal_id']}\t{proposal['note_id']}\t{proposal['title']}")
            print(f"{len(proposals)} pending proposal(s)")
        return 0
    if args.command == "approve-note":
        result = approve_note(vault, args.proposal_id)
        print(f"Approved notes/{result['note_id']}.md at revision {result['revision']}")
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
