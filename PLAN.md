# Synapse — Build Plan

Read `DESIGN.md` (why) and `AGENTS.md` (how) first. This file is the roadmap and it is the **source of truth for what is done**. Check items off as they land. A phase is finished when its checkpoint passes with **real measured output pasted in**, not when the code exists.

## Resolved open questions

- PyPI package: `synapse-memory`; CLI command: `synapse`.
- Default vault: `./synapse-vault`, keeping local data visible and project-scoped.
- Start with a fresh repository; omit the unavailable `v1-hackathon` tag and mention the London LangGraph hackathon lineage in the README.
- Keep `synapse ask` in v1 so the full retrieval experience works without an MCP client.

Build order is deliberate: the free path works end to end before a single token is spent, and the thing a visitor sees first (the dashboard and README) is built on top of something already proven.

---

## Phase 0 — Skeleton and vault

- [x] `pyproject.toml`: Python 3.11+, no runtime deps, console script `synapse`, dev extras `pytest` + `ruff`
- [x] `synapse init [path]` creates `raw/`, `wiki/`, `synapse.toml`, `synapse.db`
- [x] SQLite schema: `items` (id, source, path, title, ts, chars, built_at), `docs_fts` (FTS5 over path/title/body), `links` (from_slug, to_slug, phrase)
- [x] **FTS5 availability check at init**, with an actionable error if missing
- [x] `synapse status` prints item counts by source, unbuilt count, page count
- [x] `Vault` class: the one object everything else takes

**Checkpoint 0:** Passed on 2026-09-07 in a fresh Python 3.12.14 virtual environment with no runtime dependencies. After `synapse init ./demo`, `synapse status --vault .` was run from inside `demo`:

```text
Initialized Synapse vault at /private/tmp/synapse-checkpoint0.cVPq1z/demo
Vault: /private/tmp/synapse-checkpoint0.cVPq1z/demo
Items: 0
Unbuilt: 0
Pages: 0
Sources: none
```

---

## Phase 1 — Ingest (the free path)

- [x] `Item` / `Turn` dataclasses exactly as in `DESIGN.md` §5
- [x] Adapter registry + `@adapter("name")` decorator + detection dispatch + `--format` override
- [x] Raw writer: `raw/<source>/<YYYY-MM>/<id>.md`, write-once, skip if present, index in FTS5
- [x] **`chatgpt` adapter** — all five input shapes: folder, zip of folder, single shard, legacy `conversations.json`, `chat.html` (slice `var jsonData =`). Manifest-driven discovery. Branching-tree flatten. See `DESIGN.md` §6
- [x] **`file` adapter** — any text file, one item
- [x] **`dir` adapter** — walk a folder, one item per text file, skipping binaries and dotfiles
- [x] **Universal fallback** — an input no adapter claims still becomes one item. Never reject
- [x] Document chunking on headings with `parent` set
- [x] Trivia filter: skip conversations with < 200 chars of owner text (`--min-chars`)
- [x] `synapse search "<query>"` — CLI FTS search, so the free path is *useful* before any LLM exists
- [x] `synapse reindex` — rebuild the whole index from files

**Checkpoint 1:** Passed on 2026-09-07 against the owner's real 32-shard export. Personal search content and its source identifier are redacted and were never copied into the repository.

```text
Format: chatgpt
Conversations seen: 3138
Items added: 2044
Items skipped: 1094
  Already present: 0
  Below --min-chars: 1094
Wall time: 9.30s
API calls: 0

Search query: LangGraph
Results returned: 1
Query present in indexed hit: yes
Title, snippet, and source identifier: redacted (personal data)

Reindexed 2044 raw item(s) and 0 wiki page(s)
Items: 2044
Unbuilt: 2044
Pages: 0
Sources: chatgpt=2044
Post-reindex results: 1
```

---

## Phase 2 — LLM client and the build pass

- [x] `llm.py`: one POST to `{base_url}/chat/completions` via `urllib.request`. Timeout, one retry with backoff on 429/5xx, error messages that name the base_url. Signature is `complete(system, user) -> str` so tests inject a fake
- [x] Config resolution: `synapse.toml` then env (`SYNAPSE_BASE_URL`, `SYNAPSE_API_KEY`, `SYNAPSE_MODEL`, `owner`)
- [x] `compress(item, owner)` — owner's turns full (~1500 char cap), others truncated to ~240. `DESIGN.md` §7
- [x] Prompt assembly: page index + FTS-selected candidate pages in full + one compressed source. **Never the whole wiki**
- [x] Text-block output parser (`===PAGE:slug===` … `===END===`)
- [x] Rails in code: slug regex, must-start-with-heading, max 6 pages per source, 6000-char cap, force-append source to `## Sources`, never delete a page
- [x] `synapse build --limit N [--dry-run] [--oldest]`, resumable via `items.built_at`
- [x] `--dry-run` prints estimated input tokens **and dollars**; hard confirm above a threshold
- [x] Wikilink parser → `links` table on every page write

**Checkpoint 2:** Passed on 2026-09-07 with `gpt-4o-mini`. The first paid five-item run completed but its console metrics were lost to a command-wrapper error, so a second resumable five-item batch captured the measurements below without repeating any item. Personal page content and identifiers were never copied into the repository.

```text
Model: gpt-4o-mini
Items: 50
Estimated input tokens: 77911
Estimated output tokens: 60000
Estimated cost: $0.0477
API calls: 0

Model: gpt-4o-mini
Items: 5
Estimated input tokens: 7714
Estimated output tokens: 6000
Estimated cost: $0.0048
Built items: 5
Pages written: 14
Actual input tokens: 8216
Actual output tokens: 3383
Actual cost: $0.0033
```

Post-build structural verification across the 11 unique pages on disk:

```text
Pages starting with heading: 11
Pages within 6000 chars: 11
Pages with source paths: 11
Missing source files: 0
Valid dated fact/history lines: 52
Invalid dated fact/history lines: 0
Wikilinks: 11
Resolved wikilinks: 9
```

One generated page, with personal content redacted while preserving its measured structure:

```markdown
# [redacted title]
[redacted personal text]

## Facts
- [redacted date] [redacted personal fact]

## Related
- [[redacted-related-page]] — [redacted relationship]

## Sources
- [redacted valid raw source path]
```

---

## Phase 3 — Graph and query

- [x] `graph.py`: neighbours (one SELECT), n-hop via **recursive CTE**, subgraph around a node, orphans, degree ranking
- [x] `{nodes, edges}` JSON export; dangling links dropped
- [x] `synapse graph --json` and `synapse neighbors <slug>`
- [x] `synapse ask "<question>"` — FTS retrieve, read the top pages, one LLM call to answer with page citations

**Checkpoint 3:** Passed on 2026-09-07 against the real vault. The page identifiers, question topic, and answer are redacted as personal data.

```text
Root page: redacted (personal data)
Recursive CTE depth counts: {0: 1, 1: 1, 2: 5}
Existing wiki pages in result: 7
Recursive CTE matches independent breadth-first traversal: True

Question: [redacted real wiki topic]
Answer characters: 1582
Unique page citations: 4
Citations resolving to retrieved pages: 4
Cited pages with direct lexical evidence: 4/4
Actual cost: $0.0004
Answer and page identifiers: redacted (personal data)
```

---

## Phase 4 — Dashboard

- [x] stdlib `http.server`, **bound to 127.0.0.1 only**
- [x] REST: `/api/search`, `/api/page`, `/api/graph`, `/api/source`, `/api/status`, `/api/ingest`, `/api/build`
- [x] One HTML file: search, page reader with clickable `## Sources` chips, force-layout SVG graph, raw source viewer
- [x] Page editing writes the markdown file and reindexes just that file
- [x] Ingest and build controls with live progress
- [x] `synapse serve --demo` loads the bundled sample vault — **no API key, no import**
- [x] Build the sample vault (synthetic, ~20 interlinked pages) and commit it

**Checkpoint 4:** Passed on 2026-09-07 from an isolated, no-cache `uvx` environment. Before PyPI publication the local source package was selected explicitly; the installed command is still `synapse serve --demo`.

```text
Command: uvx --isolated --no-cache --from . synapse serve --demo
Ready in: 1.31s
Items: 5
Pages: 20
Graph nodes: 20
Graph edges: 61
API key required: no
Import required: no
```

Headless Chromium workflow verification at 1440×900:

```text
Dashboard ready: 878ms
Graph nodes: 20
Graph edges: at least 20
Search results for synthetic query: 5
Opened page: 2026 Goals
Raw source opened: yes
Page edit saved and reindexed: yes
Dry estimate: 0 items · ~0 input tokens · $0.0000
Browser console errors: 0
```

---

## Phase 5 — Agent integration

- [x] `synapse mcp` — hand-rolled stdio JSON-RPC (~120 lines): `initialize`, `tools/list`, `tools/call`
- [x] Tools: `search`, `read_page`, `list_pages`, `neighbors`, `read_source`. Descriptions must instruct **one page at a time**
- [x] Verify live in Codex CLI (the owner chose Codex as the launch client instead of the proposed Claude Code and Cursor pair); retain a client-independent stdio protocol harness
- [x] `skills/synapse/SKILL.md` for skill-based agents
- [x] Public Python API: `from synapse import Vault`

**Checkpoint 5:** in a real agent session with the MCP server configured, ask a question about the owner's history and watch the agent call `search` then `read_page` and answer correctly. Paste the tool-call sequence. Confirm **nothing from the vault is in the system prompt**.

Passed on 2026-09-07 in a fresh, ephemeral Codex CLI agent session with Synapse configured as a required local STDIO MCP server. The query, page slug, and answer are redacted as personal data.

```text
MCP initialization: passed
Agent tool calls:
1. search(query="[redacted]", limit=20)
2. read_page(slug="[redacted]")
Retrieved page supported the answer: yes
Vault page citation included: yes
Vault content or page index in the system/initial prompt: no
Client-independent stdio harness: 3 JSON-RPC responses, protocol 2025-06-18, 5 tools, 0 stray stdout lines
Tests: 29 passed in 0.20s
Ruff: all checks passed
```

---

## Phase 6 — The part that actually gets stars

Do not treat this as polish. For an adoption-driven project this phase *is* the product.

- [ ] `README.md`: hero GIF, one-line pitch, MCP block in the first screenful, three-command quickstart, tested-provider table, "how it works" in five bullets, "Not built" with reasons, v1 lineage line at the bottom
- [ ] Demo GIF: export dropped in → graph appears → agent answers from the user's own history. Fifteen seconds
- [ ] `docs/adapters.md` with the worked 30-line example, `configuration.md`, `mcp.md`, `graph.md` (the recursive-CTE piece — blog-worthy on its own), `costs.md`
- [ ] `CONTRIBUTING.md` leading with "add an adapter"
- [ ] LICENSE (MIT), GitHub Actions running `pytest` + `ruff` on 3.11/3.12/3.13
- [ ] Publish to PyPI; confirm `uvx synapse --help` works from a clean machine
- [ ] Repo hygiene: description, topics, social preview image, pinned issues for "adapter wanted"

**Checkpoint 6:** someone who has never seen the project gets from the README to a populated graph in under two minutes, following only what is written.

---

## Phase 7 — More adapters (post-launch, driven by requests)

- [ ] **`whatsapp`** — `_chat.txt`, multiple locale timestamp patterns, multi-line continuation, drop `<Media omitted>`
- [ ] **`mail`** — `.mbox` / `.eml` via stdlib, thread on `In-Reply-To`/`References`, **strip quoted reply chains**
- [ ] `claude` and `gemini` exports
- [ ] `synapse merge <a> <b>` — the human escape hatch for near-duplicate pages
- [ ] Open "adapter wanted" issues for Discord, Slack, iMessage, Signal, Notion, Bear, Apple Notes

**Checkpoint 7:** a contributor adds an adapter from `docs/adapters.md` without asking a question. That is the real test of the interface.

---

## Deliberately not in v1

Each with its trigger for reconsidering. Keeping this list honest is a trust signal; mirror it in the README.

| Not built | Reconsider when |
|---|---|
| Embeddings / `sqlite-vec` | Paraphrase recall demonstrably misses on a real corpus |
| Graph database | Never at this scale |
| PDF / DOCX adapters | Users ask, and only as an optional extra that preserves the zero-dep core |
| Auth / multi-user / sync | It stops being a local single-user tool |
| Automatic page merging | Never — human act on readable files |
| Streaming | The dashboard needs it for a chat feature |
| Agent framework | Never |

---

## Open questions for the owner

- PyPI package name (`synapse` is likely taken; CLI stays `synapse` either way).
- Default vault location: `./synapse-vault` in cwd, or `~/.synapse/vault`?
- Repo strategy: recommended is tagging the current tree `v1-hackathon` and rewriting `main`. Needs confirmation before anything destructive.
- Is `synapse ask` in scope for v1, or does MCP cover it?
