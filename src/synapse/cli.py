"""Command-line entry point."""

import argparse

from .vault import Vault


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="synapse")
    commands = root.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="create a Synapse vault")
    init.add_argument("path", nargs="?", default="./synapse-vault")

    status = commands.add_parser("status", help="show vault counts")
    status.add_argument("--vault", default="./synapse-vault")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "init":
        vault = Vault(args.path)
        vault.init()
        print(f"Initialized Synapse vault at {vault.path}")
        return 0

    vault = Vault(args.vault)
    summary = vault.status()
    print(f"Vault: {vault.path}")
    print(f"Items: {summary['items']}")
    print(f"Unbuilt: {summary['unbuilt']}")
    print(f"Pages: {summary['pages']}")
    sources = summary["sources"]
    print("Sources: " + (", ".join(f"{name}={count}" for name, count in sources.items()) or "none"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

