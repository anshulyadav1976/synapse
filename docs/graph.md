# A knowledge graph without a graph database

Every wiki page is a Markdown file. Every `[[wikilink]]` is an edge. During indexing Synapse stores those edges in one SQLite table:

```text
links(from_slug, to_slug, phrase)
```

Direct neighbours are one ordinary `SELECT`. Multi-hop traversal uses the recursive CTE SQLite has shipped for years:

```sql
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
ORDER BY depth, slug;
```

The CTE begins at one slug, follows either direction of each edge, stops at the requested depth, and collapses duplicate paths to the shortest depth. The same small index supports neighbours, local subgraphs, orphan detection, and degree ranking.

The dashboard requests `{nodes, edges}` as JSON and lays it out in inline SVG. Links to pages that do not exist are dropped at render time, so an unfinished wikilink never breaks the graph.

Why not Neo4j or another graph server? A personal knowledge graph is usually hundreds or low thousands of pages. SQLite already lives beside the full-text index, needs no service, and can be deleted and rebuilt from Markdown. A second database would make installation harder without improving the user's result at this scale.
