# Synapse — Design

> Point it at anything text. Get a searchable archive for free. Spend a few cents turning it into a wiki with a graph your agent can query.

This document is the **why**. `PLAN.md` is the **what and when**. `AGENTS.md` is the **how to work here**. Read all three before writing code.

---

## 1. What this is

Synapse turns messy text history — ChatGPT exports, WhatsApp chats, mail archives, folders of notes — into a **personal knowledge wiki with a graph**, stored as plain markdown files indexed by SQLite, queryable by any LLM agent over MCP.

It is a rewrite of a LangGraph-hackathon-winning project that used SurrealDB, FastAPI, React 19, LangGraph, and embeddings. **All of that is deliberately gone.** The lesson from v1 is that nobody adopts a personal-memory tool that requires them to run a graph database. This version is a Python package with **zero runtime dependencies** and a single-file HTML dashboard.

### The pitch, in the order the README should make it

1. A screenshot/GIF of the graph.
2. One line: what it does.
3. An MCP config block, within the first screenful, so a developer sees the integration before they scroll.

Both audiences matter: people who want to browse their own history, and developers who want a drop-in memory layer for their agent. Lead with the visual, but do not bury the MCP block.

---

## 2. The one idea that makes it simple

**Markdown is the database. SQLite is a disposable index.**

- A page is a file. An entity is a page. A fact is a dated line in that file. An edge is a `[[wikilink]]` inside it.
- SQLite holds nothing authoritative. Delete `synapse.db` and `synapse reindex` rebuilds it from the files in seconds.
- Consequences, all free: your data works in Obsidian, git, `grep`, and any editor; backup is copying a folder; "how do I inspect what it stored" stops being a question; there is no migration story.

Everything else in this design follows from that decision.

---

## 3. Vault layout

```
my-brain/                        # a "vault" — the Obsidian word, chosen deliberately
  raw/<source>/<YYYY-MM>/<id>.md # immutable, one file per ingested item
  wiki/<slug>.md                 # LLM-maintained, human-editable
  synapse.db                     # derived index — safe to delete
  synapse.toml                   # vault config (model, base_url, owner name)
```

- `raw/` is **never rewritten**. Write-once. If a file exists, skip it.
- `wiki/` is derived and can always be regenerated from `raw/`.
- `synapse init ./my-brain` creates the structure. `SYNAPSE_VAULT` env var or `--vault` selects it; default `./synapse-vault` in cwd, or `~/.synapse/vault` if that is nicer for a global install.

---

## 4. The two phases, and why the split is the most important decision in the project

### Ingest is free

No model call. Parse the input, write `raw/` markdown, index in FTS5.

- A 3,000-conversation ChatGPT export is about a minute of CPU and **zero dollars**.
- Everything is full-text searchable the moment it lands.
- **A user can try Synapse, see real value, and never enter an API key.** This is the single biggest adoption lever in the project. Protect it.

### Build costs money

The LLM pass: one item in, zero or more page writes out.

- A plain `for` loop over unprocessed items. **Not** an agent framework, not a graph of nodes. Say so in the README; for a tool people are deciding whether to trust, "the pipeline is a for-loop" is a feature.
- Resumable: each item is marked processed, so `--limit 20` can be run repeatedly and never redoes work.
- `--dry-run` prints a token and dollar estimate and sends nothing. **Above a threshold (say 200k input tokens) require an explicit confirm.** A surprise bill is how you permanently lose a user.

### Why the phases must stay separate

Re-running the wiki pass must never re-pay for parsing, and someone must be able to get value with no credentials. If these two ever merge into one command, both properties die.

---

## 5. Ingest architecture: formats stop at the door

v1 had adapters for chatgpt, claude, gemini, txt, md, json, pdf, docx, all tangled into the storage layer. That is a treadmill. Instead:

- **Layer 1 — readers.** Turn an input into a stream of `Item`s. Nothing else.
- **Layer 2 — everything downstream.** Raw writing, indexing, the build pass. Sees only `Item`s. **Format never leaks past layer 1.**

### The Item contract — keep it this small

```python
@dataclass
class Turn:
    speaker: str          # display name, or "assistant" / "me"
    text: str
    ts: str | None = None # ISO8601

@dataclass
class Item:
    id: str               # stable across re-runs; dedup key
    source: str           # "chatgpt" | "whatsapp" | "mail" | "file" | ...
    title: str
    ts: str               # ISO8601 — REQUIRED, see below
    text: str | None = None      # for documents
    turns: list[Turn] | None = None  # for conversations
    parent: str | None = None    # chunk of a larger document
```

`turns` is the only meaningful extension, because most interesting sources are conversational: ChatGPT, Claude, WhatsApp, Telegram, iMessage, Discord, Slack, and email threads all fit one shape.

### The adapter registry is the community surface

Make adding a format a **30-line pull request**. If a contributor has to understand storage to add Discord support, nobody contributes; if it is one function, you will be sent adapters for Discord, Slack, iMessage, Signal, Bear, Notion, and Apple Notes. That is how this repo gets forks.

```python
@adapter("whatsapp")
def read(path: Path) -> Iterator[Item]:
    ...
```

Put "add an adapter" at the top of `CONTRIBUTING.md`, with WhatsApp as the worked example and a test harness that is *a fixture file plus an expected item count*.

### Two rules that make "format shouldn't matter" structurally true

- **Never reject an input.** If no adapter claims a file, the fallback makes it one text item. Worst case the user still gets full-text search immediately and the build pass still extracts entities. This promise is the whole pitch, so it must be guaranteed by the code path, not by best effort.
- **Detect, don't declare.** Sniff the input; keep `--format` as an override. A folder containing `export_manifest.json` is a ChatGPT export. A `.txt` whose lines match `[date, time] Name: text` is WhatsApp. An `.mbox` is mail. A folder of `.md` is notes.

### Chunking

A 500-page book as one item is useless to both search and the build pass. Split long documents on headings with a size target (~6–8k chars), set `parent` on each chunk so provenance can still point at the whole document.

### Why adapters exist at all, given the LLM does the understanding

This question will come up; the answer belongs in the docs. Adapters do **not** interpret content — the model does. They exist for three things that are trivial to parse deterministically and unreliable to infer:

1. **Boundaries.** The build pass is one bounded call per item. Boundaries are what make it chunkable, resumable, priceable, and skippable. A whole export as one blob cannot be `--limit`ed, resumed, or estimated.
2. **Timestamps.** Every fact is a dated line and `## History` ranges depend on real dates. Dates come from the export's structured fields. A model asked to infer dates from prose will confidently invent them, which silently poisons the mechanism that replaces validity windows.
3. **Speaker identity.** The compression rule (§7) needs to know whose words are whose.

Plus: stable item IDs enable skip-if-processed and trivia filtering, so re-runs never re-pay; and `## Sources` needs a stable path.

This is also why the unknown-format fallback is *acceptable rather than good*: you get an item, an mtime, and search, but no real dates and no speakers, so the resulting wiki is thinner. Document that tradeoff honestly.

---

## 6. The real ChatGPT export format (verified September 2026)

This was checked against an actual 2026 export. **Do not trust older blog posts or v1's parser.**

- **It is an extracted folder, not a zip**, and there is **no `conversations.json`**.
- Conversations are **sharded**: `conversations-000.json` … `conversations-031.json`, 100 conversations per shard. The sample had **3,138 conversations across 32 shards**, ~92 MB of JSON.
- **`export_manifest.json` lists every file** in the export. Use it for discovery; it is more reliable than globbing.
- **`chat.html` is a 135 MB redundant viewer.** One `<script>` containing `var jsonData = [...]` — the same conversation objects — plus a renderer. Never parse the HTML as HTML. If a user only has `chat.html`, slice out that single assignment and parse it as JSON.
- Per-conversation shape is **unchanged from older exports**: `conversation_id`, `id`, `create_time`, `title`, and a `mapping` tree whose nodes carry `message.author.role` and `message.content.parts` (a list).
- The `mapping` is a **tree that branches** (regenerated answers). Walking every node in time order and keeping text parts is simpler than choosing a branch and loses nothing for a knowledge base about a person.
- Also present and worth ingesting later: `user.json`, `shared_conversations.json`, `codex.json`, `message_feedback.json`, and ~1,250 `.dat` asset blobs.

**Support all of:** a folder, a zip of that folder, a single shard, a legacy `conversations.json`, and `chat.html` as a last resort.

### Trivia filter

Skip conversations with **under 200 characters of the owner's own text**. "fix this regex" says nothing about a person. Make the threshold a flag (`--min-chars`).

---

## 7. The compression rule, generalized

The token-cost trick: **the owner's turns go in full (capped ~1500 chars each); everyone else's are truncated to ~240 chars.** In a chat log the human side is the signal about the human, and the model already knows roughly what an assistant would have said.

Because `Item.turns` has named speakers, this generalizes from ChatGPT to WhatsApp group chats, mail threads, Discord, and iMessage with **one config value**: who the owner is (`owner = "Anshu"` in `synapse.toml`, with aliases, inferable from a ChatGPT export). Roughly halves input tokens on every conversational source.

---

## 8. The build pass

For each unprocessed item, one LLM call whose user message contains exactly three sections:

1. **The page index** — every page's slug and title. A few hundred tokens for hundreds of pages.
2. **Candidate pages in full** — only the handful FTS says are relevant to this item's title/content.
3. **The one compressed source.**

**Index, not corpus.** This is what stops the model minting `the-home-server` next to `home-server`, and it is why cost stays flat as the wiki grows. Never send the whole wiki.

### Output protocol: text blocks, not JSON mode

```
===PAGE:<slug>===
<full page markdown>
===END===
===SUMMARY===
<one line>
===END===
```

**Do not use JSON mode or tool calling.** Support for both is uneven across OpenAI-compatible providers, and a text protocol works on literally everything including small local models. This is a compatibility decision, not a stylistic one.

### Rails enforced in code, not merely requested in the prompt

- Slug must match `^[a-z0-9][a-z0-9-]{0,60}$`.
- Page content must start with a heading.
- Max 6 pages written per source.
- Page capped at ~6000 chars.
- If the model omitted the source path, **append it to `## Sources` yourself**. Provenance is non-negotiable.
- **The pass never deletes a page.** Deletion is a human act.

---

## 9. Page schema

```markdown
# Title
One line: what this is and why it matters to the owner.

## Facts
- [2024-09-14] one durable fact per line, newest first; "(inferred)" when inferred

## History
- [2023-01-02 → 2024-09-14] a fact that stopped being true, with when

## Related
- [[other-slug]] — one phrase on the relationship

## Sources
- raw/chatgpt/2024-09/chatgpt-abc123.md
```

- **Dated facts** give validity windows with no database.
- **`## History`** is why a fact never silently vanishes; superseded facts move here with a range.
- **`## Sources`** is provenance; the dashboard turns each into a chip that opens the immutable raw item.
- **`## Related`** is the graph.

---

## 10. The graph, without a graph database

This deserves its own section in the README, because everyone assumes Neo4j is required.

- Parse `[[slug]]` out of each page on write into `links(from_slug, to_slug, phrase)`.
- Neighbours: one `SELECT`. Multi-hop traversal: a **recursive CTE**, which SQLite has had for over a decade. ~10 lines of SQL replaces a graph engine.
- Shortest path, subgraph-around-a-node, orphan pages, most-connected entities: all plain queries.
- Serve `{nodes, edges}` as JSON; lay out client-side. **Drop dangling links at render** rather than storing broken edges.
- Node size by degree. Click a node to open the page.

A personal knowledge graph is hundreds to low thousands of nodes. A graph database solves a problem that does not exist at this scale, and costs you every visitor unwilling to run a second server.

---

## 11. LLM configuration: any OpenAI-compatible endpoint, no SDK

- Three settings, from `synapse.toml` or env: `SYNAPSE_BASE_URL`, `SYNAPSE_API_KEY`, `SYNAPSE_MODEL`.
- **Do not depend on the `openai` package.** One POST to `{base_url}/chat/completions` with `urllib.request` is ~20 lines. No SDK version churn, no auth abstraction to fight, and it genuinely works with every provider.
- Ship a **tested provider table** in the README (OpenAI, OpenRouter, Groq, Together, DeepSeek, Ollama at `http://localhost:11434/v1`, LM Studio). "Will it work with my provider" is the first question every visitor has; answering it in a table is itself a star magnet.
- Because it is one plain call with no framework, the whole thing runs against a local model **offline and free**. Say that loudly.
- Handle: timeouts, one retry with backoff on 429/5xx, and a clear error naming the base_url when auth fails.

---

## 12. Dashboard: one HTML file

- Vanilla JS and inline SVG, served by stdlib `http.server` from the same process. **No React, no Vite, no bundler, no `node_modules`.**
- Views: search, page reader with source chips, the graph, raw source viewer, and controls for ingest and build with live progress.
- "The dashboard is a single HTML file you can read" is a feature, and it makes `uvx synapse serve` genuinely one command with no build step.
- Skipping FastAPI drops uvicorn, starlette, and pydantic. For one local user, async buys nothing.
- Bind **127.0.0.1 only**. This is personal data; never bind 0.0.0.0 by default.
- Pages are editable from the dashboard (write straight to the markdown file, then reindex that file). Human correction is the answer to bad entity resolution.

---

## 13. Agent integration

Four surfaces over one core module. The core is a Python API; everything else is a thin wrapper.

- **MCP server** (`synapse mcp`), stdio. Tools: `search`, `read_page`, `list_pages`, `neighbors`, `read_source`. One config block works in Claude Code, Cursor, Windsurf, Cline, and anything else speaking MCP. **Hand-roll the stdio JSON-RPC loop (~120 lines, stdlib)** rather than depending on the `mcp` package, which pulls pydantic, starlette, uvicorn and friends for transports we do not use. "The MCP server is 120 lines of stdlib" is a selling point. Note in the docs that HTTP transport would justify the SDK.
- **Skill folder** (`skills/synapse/SKILL.md`) for Claude-style agents that prefer skills over MCP.
- **Python API**: `from synapse import Vault; Vault("./my-brain").search("...")`.
- **REST**: a few `GET /api/...` endpoints from the same server the dashboard uses.

Post-launch agent writes stay deliberately asymmetric. MCP may stage an append-only semantic note under a separate `notes/` namespace, but it cannot approve, merge, delete, or touch `raw/`. Every proposal carries a stable note ID, provenance, idempotency key, and parent revision, and returns a diff. A human commits it through the CLI. Operational state such as credentials, browser profiles, live sessions, and account routing never enters semantic memory or the graph.

### The principle to advertise

**Nothing is injected into the agent's prompt.** Not the page index, not a summary. Tool descriptions instruct the agent to read one page at a time. A thousand pages cost zero tokens until one is opened.

Every competing memory product stuffs context and burns tokens on every turn. Put this in the README as a differentiator.

---

## 14. Packaging and the demo

- **`uvx --from synapse-vault synapse`** for zero-install. Largest single adoption lever in Python today. The intended `synapse-memory` distribution name and `synapse` are both owned on PyPI, so publish as `synapse-vault`; the CLI remains `synapse`.
- **Zero runtime dependencies.** Python 3.11+, stdlib only: `sqlite3`, `urllib.request`, `http.server`, `json`, `zipfile`, `mailbox`, `email`, `tomllib`. Dev dependencies (pytest, ruff) do not count. This is a headline that contrasts hard with v1 and with every competitor.
- **Ship a sample vault** so `uvx synapse serve --demo` shows a populated graph with **no API key and no import**. Let people see it in ten seconds before it asks for anything.
- Verify FTS5 is available at `init` and fail with a clear, actionable message rather than a cryptic SQL error.
- The demo GIF: drop in an export → graph appears → an agent answers a question about the user's own history. That sequence is the entire pitch in fifteen seconds.

---

## 15. Per-format traps

- **Email** (`.mbox`, `.eml`): stdlib `mailbox` + `email` do everything. Thread on `In-Reply-To` / `References` into conversations. **Strip quoted reply chains** (`>` blocks, "On ... wrote:") or you ingest the same paragraph forty times and pay for it in the build pass. Prefer `text/plain` parts; decode MIME properly.
- **WhatsApp**: parse `_chat.txt` from the export zip. The trap is that timestamp format follows the exporting phone's **locale** — date order and 12h/24h both vary, so try several patterns and record which matched. Multi-line messages appear as continuation lines with no timestamp: accumulate until the next line that matches the pattern. Drop `<Media omitted>`.
- **ChatGPT**: shards, manifest, branching tree — see §6.
- **PDF/DOCX**: **out of scope for v1.** They pull real dependencies for a minority of inputs and would break the zero-dependency claim. Document `markitdown` or `pandoc` as a one-line preprocessing step, and revisit only if users ask.

---

## 16. Risks, and how the design answers them

| Risk | Mitigation |
|---|---|
| The ChatGPT parser rots when OpenAI changes the format | Format **detection** plus fixture-based tests; `--format` override; support five input shapes (§6) |
| FTS5 missing from a user's Python SQLite build | Check at `init`, fail with an actionable message |
| Cost surprise on a large export | `--dry-run` estimates; hard confirm above a token threshold; bounded `--limit`; resumable |
| Prompt injection via imported history reaching agent context | Wiki pages become agent context, so say so in the README. Never execute anything from page content. A `## Sources` chip lets the user trace any suspicious fact to its origin |
| Near-duplicate pages | The page index in the prompt reduces it; ship `synapse merge <a> <b>` as the human escape hatch. **Do not automate merging** |
| Personal data leaking into the repo | Fixtures must be synthetic or anonymised. **Never commit a real export.** See `AGENTS.md` |

---

## 17. Explicit non-goals for v1

Each of these is a "no" with a reason, and the reasons belong in the README's own "Not built" section — stating them is a trust signal.

- **Embeddings / vector search.** FTS5 first. Add behind a flag only if paraphrase recall demonstrably misses on a real corpus. Embeddings add an API dependency, a cost per item, and a migration.
- **A graph database.** See §10.
- **Auth / multi-user / cloud sync.** It is a local single-user tool.
- **An agent framework.** The pipeline is a for-loop.
- **Automatic page merging or deletion.** Human acts on files you can read.
- **PDF/DOCX adapters.** See §15.
- **Streaming responses.** The build pass is batch; the dashboard can wait.

---

## 18. Naming and repo strategy

- Name: **Synapse**, reusing the hackathon name. Recommendation: in `github.com/anshulyadav1976/synapse`, tag the current tree `v1-hackathon` so the LangGraph win stays provable and linkable, then make `main` this version. One name, one link, and visitors land on something they would actually run.
- The README should mention the v1 lineage in one line near the bottom ("won the LangGraph hackathon; this is the rewrite that deleted the database"). It is a good story and it explains the design's opinions.
