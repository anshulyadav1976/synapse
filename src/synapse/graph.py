"""A personal-scale graph using plain SQLite queries."""

import re

from .db import connect
from .vault import Vault


def _pages(vault: Vault) -> dict[str, str]:
    pages = {}
    for path in vault.wiki_path.glob("*.md"):
        if path.name.startswith("."):
            continue
        body = path.read_text(encoding="utf-8")
        heading = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        pages[path.stem] = heading.group(1).strip() if heading else path.stem
    return pages


def neighbors(vault: Vault, slug: str) -> list[dict[str, str]]:
    with connect(vault.db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                CASE WHEN from_slug = ? THEN to_slug ELSE from_slug END AS slug,
                CASE WHEN from_slug = ? THEN 'out' ELSE 'in' END AS direction,
                phrase
            FROM links
            WHERE from_slug = ? OR to_slug = ?
            ORDER BY slug
            """,
            (slug, slug, slug, slug),
        )
        return [dict(row) for row in rows]


def n_hop(vault: Vault, slug: str, hops: int) -> list[dict[str, int | str]]:
    with connect(vault.db_path) as connection:
        rows = connection.execute(
            """
            WITH RECURSIVE reach(slug, depth) AS (
                VALUES (?, 0)
                UNION
                SELECT
                    CASE WHEN links.from_slug = reach.slug
                         THEN links.to_slug ELSE links.from_slug END,
                    reach.depth + 1
                FROM reach
                JOIN links
                  ON links.from_slug = reach.slug OR links.to_slug = reach.slug
                WHERE reach.depth < ?
            )
            SELECT slug, min(depth) AS depth
            FROM reach
            GROUP BY slug
            ORDER BY depth, slug
            """,
            (slug, hops),
        )
        return [dict(row) for row in rows]


def subgraph(vault: Vault, slug: str, hops: int = 1) -> dict[str, list[dict[str, object]]]:
    reachable = {row["slug"] for row in n_hop(vault, slug, hops)}
    graph = graph_json(vault)
    return {
        "nodes": [node for node in graph["nodes"] if node["id"] in reachable],
        "edges": [
            edge
            for edge in graph["edges"]
            if edge["source"] in reachable and edge["target"] in reachable
        ],
    }


def graph_json(vault: Vault) -> dict[str, list[dict[str, object]]]:
    pages = _pages(vault)
    with connect(vault.db_path) as connection:
        rows = connection.execute(
            "SELECT from_slug, to_slug, phrase FROM links ORDER BY from_slug, to_slug"
        ).fetchall()
    edges = [
        {"source": row["from_slug"], "target": row["to_slug"], "phrase": row["phrase"]}
        for row in rows
        if row["from_slug"] in pages and row["to_slug"] in pages
    ]
    degrees = {slug: 0 for slug in pages}
    for edge in edges:
        degrees[edge["source"]] += 1
        degrees[edge["target"]] += 1
    nodes = [
        {"id": slug, "title": title, "degree": degrees[slug]}
        for slug, title in sorted(pages.items())
    ]
    return {"nodes": nodes, "edges": edges}


def orphans(vault: Vault) -> list[str]:
    return [node["id"] for node in graph_json(vault)["nodes"] if node["degree"] == 0]


def degree_ranking(vault: Vault) -> list[tuple[str, int]]:
    return sorted(
        ((node["id"], node["degree"]) for node in graph_json(vault)["nodes"]),
        key=lambda entry: (-entry[1], entry[0]),
    )

