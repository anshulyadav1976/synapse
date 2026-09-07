from synapse import Vault
from synapse.db import connect
from synapse.graph import degree_ranking, graph_json, n_hop, neighbors, orphans, subgraph
from synapse.index import index_document, replace_links


def _graph_vault(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.init()
    pages = {
        "alpha": "# Alpha\n\n- [[beta]] — knows\n- [[missing]] — dangling\n",
        "beta": "# Beta\n\n- [[gamma]] — follows\n",
        "gamma": "# Gamma\n",
        "orphan": "# Orphan\n",
    }
    with connect(vault.db_path) as connection:
        for slug, body in pages.items():
            path = vault.wiki_path / f"{slug}.md"
            path.write_text(body)
            index_document(connection, f"wiki/{slug}.md", slug.title(), body)
            replace_links(connection, slug, body)
    return vault


def test_neighbors_and_recursive_cte(tmp_path):
    vault = _graph_vault(tmp_path)
    assert neighbors(vault, "beta") == [
        {"slug": "alpha", "direction": "in", "phrase": "knows"},
        {"slug": "gamma", "direction": "out", "phrase": "follows"},
    ]
    assert n_hop(vault, "alpha", 2) == [
        {"slug": "alpha", "depth": 0},
        {"slug": "beta", "depth": 1},
        {"slug": "missing", "depth": 1},
        {"slug": "gamma", "depth": 2},
    ]


def test_graph_export_drops_dangling_links_and_reports_views(tmp_path):
    vault = _graph_vault(tmp_path)
    graph = graph_json(vault)
    assert len(graph["nodes"]) == 4
    assert len(graph["edges"]) == 2
    assert all(edge["target"] != "missing" for edge in graph["edges"])
    assert orphans(vault) == ["orphan"]
    assert degree_ranking(vault)[0] == ("beta", 2)
    around = subgraph(vault, "beta", 1)
    assert {node["id"] for node in around["nodes"]} == {"alpha", "beta", "gamma"}

