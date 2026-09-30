"""The vault shared by every Synapse surface."""

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .config import Config, load
from .db import connect, initialize

DEFAULT_CONFIG = """# Synapse vault configuration
owner = ""
base_url = "https://api.openai.com/v1"
model = "gpt-4o-mini"
embedding_model = "text-embedding-3-small"
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
        initialize(self.db_path)
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
            semantic_chunks = connection.execute("SELECT count(*) FROM embeddings").fetchone()[0]
            semantic_models = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT model FROM embeddings ORDER BY model"
                )
            ]
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
            "semantic_chunks": semantic_chunks,
            "semantic_models": semantic_models,
        }

    def search(
        self,
        query: str,
        limit: int = 10,
        *,
        hybrid: bool = False,
        after: str | None = None,
        before: str | None = None,
        source: str | None = None,
        kind: str | None = None,
        embed: Callable[[list[str]], list[list[float]]] | None = None,
    ) -> list[dict[str, str]]:
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"No Synapse vault found at {self.path}. Run: synapse init {self.path}"
            )
        if limit < 1:
            return []
        for label, value in (("after", after), ("before", before)):
            try:
                if value:
                    datetime.fromisoformat(value)
            except ValueError as error:
                raise ValueError(f"{label} must be an ISO date such as 2026-09-30") from error
        if kind not in {None, "raw", "wiki", "note"}:
            raise ValueError("kind must be raw, wiki, or note")

        initialize(self.db_path)
        from .index import search

        query_vector = None
        embedding_model = None
        if hybrid:
            config = self.config()
            embedding_model = config.embedding_model
            with connect(self.db_path) as connection:
                count = connection.execute(
                    "SELECT count(*) FROM embeddings WHERE model = ?", (embedding_model,)
                ).fetchone()[0]
            if not count:
                raise RuntimeError(
                    f'No semantic index for {embedding_model}. Run: synapse embed --vault "{self.path}"'
                )
            if embed is None:
                if not config.embedding_api_key and not config.embedding_base_url.startswith(
                    ("http://localhost", "http://127.0.0.1")
                ):
                    raise RuntimeError(
                        "No embedding API key configured. Set SYNAPSE_EMBEDDING_API_KEY "
                        "or SYNAPSE_API_KEY."
                    )
                from .llm import OpenAICompatible

                embed = OpenAICompatible(
                    config.embedding_base_url,
                    config.embedding_api_key,
                    embedding_model,
                ).embed
            vectors = embed([query])
            if len(vectors) != 1:
                raise RuntimeError("Embedding endpoint returned the wrong number of vectors")
            query_vector = vectors[0]
        return search(
            self.db_path,
            query,
            limit,
            query_vector=query_vector,
            embedding_model=embedding_model,
            after=after,
            before=before,
            source=source,
            kind=kind,
        )

    def config(self) -> Config:
        return load(self.config_path)
