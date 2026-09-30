"""Vault configuration with environment overrides."""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    owner: str = ""
    input_cost_per_million: float = 0.15
    output_cost_per_million: float = 0.60
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"


def load(path: Path) -> Config:
    values = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    base_url = os.environ.get("SYNAPSE_BASE_URL", values.get("base_url", Config.base_url))
    api_key = os.environ.get("SYNAPSE_API_KEY", values.get("api_key", ""))
    return Config(
        base_url=base_url,
        api_key=api_key,
        model=os.environ.get("SYNAPSE_MODEL", values.get("model", Config.model)),
        owner=os.environ.get("SYNAPSE_OWNER", values.get("owner", "")),
        input_cost_per_million=float(
            os.environ.get(
                "SYNAPSE_INPUT_COST_PER_MILLION",
                values.get("input_cost_per_million", Config.input_cost_per_million),
            )
        ),
        output_cost_per_million=float(
            os.environ.get(
                "SYNAPSE_OUTPUT_COST_PER_MILLION",
                values.get("output_cost_per_million", Config.output_cost_per_million),
            )
        ),
        embedding_base_url=os.environ.get(
            "SYNAPSE_EMBEDDING_BASE_URL", values.get("embedding_base_url", base_url)
        ),
        embedding_api_key=os.environ.get(
            "SYNAPSE_EMBEDDING_API_KEY", values.get("embedding_api_key", api_key)
        ),
        embedding_model=os.environ.get(
            "SYNAPSE_EMBEDDING_MODEL",
            values.get("embedding_model", Config.embedding_model),
        ),
    )
