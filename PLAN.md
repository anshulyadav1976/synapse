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

- [ ] `Item` / `Turn` dataclasses exactly as in `DESIGN.md` §5
- [ ] Adapter registry + `@adapter("name")` decorator + detection dispatch + `--format` override
- [ ] Raw writer: `raw/<source>/<YYYY-MM>/<id>.md`, write-once, skip if present, index in FTS5
- [ ] **`chatgpt` adapter** — all five input shapes: folder, zip of folder, single shard, legacy `conversations.json`, `chat.html` (slice `var jsonData =`). Manifest-driven discovery. Branching-tree flatten. See `DESIGN.md` §6
- [ ] **`file` adapter** — any text file, one item
- [ ] **`dir` adapter** — walk a folder, one item per text file, skipping binaries and dotfiles
- [ ] **Universal fallback** — an input no adapter claims still becomes one item. Never reject
- [ ] Document chunking on headings with `parent` set
- [ ] Trivia filter: skip conversations with < 200 chars of owner text (`--min-chars`)
- [ ] `synapse search "<query>"` — CLI FTS search, so the free path is *useful* before any LLM exists
- [ ] `synapse reindex` — rebuild the whole index from files

**Checkpoint 1:** the owner runs ingest on their real ~92 MB / 3,138-conversation export. Record: conversations seen, items added, items skipped, wall time, and a `synapse search` hit that returns something sensible. **Zero API calls made.** This is the moment the project is already worth using.

---

## Phase 2 — LLM client and the build pass

- [ ] `llm.py`: one POST to `{base_url}/chat/completions` via `urllib.request`. Timeout, one retry with backoff on 429/5xx, error messages that name the base_url. Signature is `complete(system, user) -> str` so tests inject a fake
- [ ] Config resolution: `synapse.toml` then env (`SYNAPSE_BASE_URL`, `SYNAPSE_API_KEY`, `SYNAPSE_MODEL`, `owner`)
- [ ] `compress(item, owner)` — owner's turns full (~1500 char cap), others truncated to ~240. `DESIGN.md` §7
- [ ] Prompt assembly: page index + FTS-selected candidate pages in full + one compressed source. **Never the whole wiki**
- [ ] Text-block output parser (`===PAGE:slug===` … `===END===`)
- [ ] Rails in code: slug regex, must-start-with-heading, max 6 pages per source, 6000-char cap, force-append source to `## Sources`, never delete a page
- [ ] `synapse build --limit N [--dry-run] [--oldest]`, resumable via `items.built_at`
- [ ] `--dry-run` prints estimated input tokens **and dollars**; hard confirm above a threshold
- [ ] Wikilink parser → `links` table on every page write

**Checkpoint 2:** `synapse build --dry-run --limit 50` prints a cost estimate and sends nothing. Then `synapse build --limit 5` against a real provider produces valid pages with correct dates, real `## Sources` paths, and `[[links]]` that resolve. Paste one generated page verbatim (redact personal content if needed) and the actual cost.

---

## Phase 3 — Graph and query

- [ ] `graph.py`: neighbours (one SELECT), n-hop via **recursive CTE**, subgraph around a node, orphans, degree ranking
- [ ] `{nodes, edges}` JSON export; dangling links dropped
- [ ] `synapse graph --json` and `synapse neighbors <slug>`
- [ ] `synapse ask "<question>"` — FTS retrieve, read the top pages, one LLM call to answer with page citations

**Checkpoint 3:** a recursive-CTE 2-hop query on the real vault returns the right pages, and `synapse ask` answers a question about the owner's own history citing pages that actually contain the fact.

---

## Phase 4 — Dashboard

- [ ] stdlib `http.server`, **bound to 127.0.0.1 only**
- [ ] REST: `/api/search`, `/api/page`, `/api/graph`, `/api/source`, `/api/status`, `/api/ingest`, `/api/build`
- [ ] One HTML file: search, page reader with clickable `## Sources` chips, force-layout SVG graph, raw source viewer
- [ ] Page editing writes the markdown file and reindexes just that file
- [ ] Ingest and build controls with live progress
- [ ] `synapse serve --demo` loads the bundled sample vault — **no API key, no import**
- [ ] Build the sample vault (synthetic, ~20 interlinked pages) and commit it

**Checkpoint 4:** `uvx synapse serve --demo` on a clean machine shows a populated graph in under ten seconds with no configuration. This is the ten-second experience every visitor gets; it must be flawless.

---

## Phase 5 — Agent integration

- [ ] `synapse mcp` — hand-rolled stdio JSON-RPC (~120 lines): `initialize`, `tools/list`, `tools/call`
- [ ] Tools: `search`, `read_page`, `list_pages`, `neighbors`, `read_source`. Descriptions must instruct **one page at a time**
- [ ] Verify live in **at least two** MCP clients (Claude Code and Cursor)
- [ ] `skills/synapse/SKILL.md` for skill-based agents
- [ ] Public Python API: `from synapse import Vault`

**Checkpoint 5:** in a real agent session with the MCP server configured, ask a question about the owner's history and watch the agent call `search` then `read_page` and answer correctly. Paste the tool-call sequence. Confirm **nothing from the vault is in the system prompt**.

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
