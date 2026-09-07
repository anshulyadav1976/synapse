"""Command-line entry point."""

import argparse
import time

from .index import reindex
from .ingest import ingest
from .vault import Vault


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="synapse")
    commands = root.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="create a Synapse vault")
    init.add_argument("path", nargs="?", default="./synapse-vault")

    status = commands.add_parser("status", help="show vault counts")
    status.add_argument("--vault", default="./synapse-vault")

    ingest_command = commands.add_parser("ingest", help="import text without API calls")
    ingest_command.add_argument("input")
    ingest_command.add_argument("--vault", default="./synapse-vault")
    ingest_command.add_argument("--format", dest="format_name")
    ingest_command.add_argument("--min-chars", type=int, default=200)

    search = commands.add_parser("search", help="full-text search the vault")
    search.add_argument("query")
    search.add_argument("--vault", default="./synapse-vault")
    search.add_argument("--limit", type=int, default=10)

    rebuild = commands.add_parser("reindex", help="rebuild SQLite from Markdown")
    rebuild.add_argument("--vault", default="./synapse-vault")
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
        result = ingest(vault, args.input, args.format_name, args.min_chars)
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
    raw_count, page_count = reindex(vault.path)
    print(f"Reindexed {raw_count} raw item(s) and {page_count} wiki page(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
