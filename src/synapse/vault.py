"""The vault shared by every Synapse surface."""

import json
from pathlib import Path

from .config import Config, load
from .db import connect, initialize

DEFAULT_CONFIG = """# Synapse vault configuration
owner = ""
base_url = "https://api.openai.com/v1"
model = "gpt-4o-mini"
input_cost_per_million = 0.15
output_cost_per_million = 0.60
"""


class Vault:
    def __init__(self, path: str | Path = "./synapse-vault") -> None:
        self.path = Path(path).expanduser().resolve()
        self.raw_path = self.path / "raw"
        self.wiki_path = self.path / "wiki"
        self.notes_path = self.path / "notes"
        self.proposals_path = self.path / ".synapse" / "proposals"
        self.db_path = self.path / "synapse.db"
        self.config_path = self.path / "synapse.toml"

    def init(self) -> None:
        self.raw_path.mkdir(parents=True, exist_ok=True)
        self.wiki_path.mkdir(parents=True, exist_ok=True)
        self.notes_path.mkdir(parents=True, exist_ok=True)
        self.proposals_path.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists():
            self.config_path.write_text(DEFAULT_CONFIG, encoding="utf-8")
        initialize(self.db_path)

    def status(self) -> dict[str, object]:
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"No Synapse vault found at {self.path}. Run: synapse init {self.path}"
            )
        with connect(self.db_path) as connection:
            sources = {
                row["source"]: row["count"]
                for row in connection.execute(
                    "SELECT source, count(*) AS count FROM items GROUP BY source ORDER BY source"
                )
            }
            items = connection.execute("SELECT count(*) FROM items").fetchone()[0]
            unbuilt = connection.execute(
                "SELECT count(*) FROM items WHERE built_at IS NULL"
            ).fetchone()[0]
        pages = sum(
            1
            for path in self.wiki_path.glob("*.md")
            if path.is_file() and not path.name.startswith(".")
        )
        notes = sum(1 for path in self.notes_path.glob("*.md") if path.is_file())
        proposals = sum(
            1
            for path in self.proposals_path.glob("*.json")
            if json.loads(path.read_text(encoding="utf-8"))["status"] == "pending"
        )
        return {
            "items": items,
            "unbuilt": unbuilt,
            "pages": pages,
            "notes": notes,
            "proposals": proposals,
            "sources": sources,
        }

    def search(self, query: str, limit: int = 10) -> list[dict[str, str]]:
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"No Synapse vault found at {self.path}. Run: synapse init {self.path}"
            )
        from .index import search

        return search(self.db_path, query, limit)

    def config(self) -> Config:
        return load(self.config_path)
