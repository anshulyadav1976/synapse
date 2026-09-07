# AGENTS.md — how to work in this repo

Read `DESIGN.md` (the why) and `PLAN.md` (the what and when) first. This file is the **how**. It overrides your defaults.

---

## The prime directive

**This project's entire value proposition is that it is small.** It is a rewrite of a heavier version that nobody adopted. Every dependency, every abstraction, and every clever layer you add makes the pitch less true and the project less likely to be starred, forked, or used.

When in doubt: fewer files, fewer deps, fewer concepts, shorter diff.

## Hard rules — do not violate these without the owner saying so explicitly

1. **Zero runtime dependencies.** Python 3.11+, stdlib only. `sqlite3`, `urllib.request`, `http.server`, `json`, `zipfile`, `mailbox`, `email`, `tomllib`, `dataclasses`, `re`, `pathlib`. Dev deps (`pytest`, `ruff`) are fine and are the only exception. If you think you need a runtime dependency, stop and write the reason in `PLAN.md` under "Open questions" instead of adding it.
2. **No `openai` package.** One POST with `urllib.request`. See `DESIGN.md` §11.
3. **No `mcp` package.** Hand-roll the stdio JSON-RPC loop. See `DESIGN.md` §13.
4. **No web framework.** stdlib `http.server`.
5. **No frontend build step.** One HTML file, vanilla JS, inline SVG. No React, no bundler, no `node_modules`, no CDN `<script>` tags for libraries — inline what you need.
6. **No graph database, no embeddings, no vector store** in v1. See `DESIGN.md` §10 and §17.
7. **No agent framework.** The build pass is a `for` loop.
8. **Markdown is authoritative; SQLite is disposable.** Never store a fact only in the database. `synapse reindex` must be able to rebuild the entire index from the files.
9. **`raw/` is write-once.** Never overwrite or edit an existing raw file.
10. **Never commit personal data.** Test fixtures are synthetic or thoroughly anonymised, and small (a handful of KB). The owner has a real 92 MB export on their machine for manual verification — it must never enter the repo, not in tests, not in docs, not in an example. If you need a fixture that mirrors a real format, hand-write a minimal synthetic one.

## Code conventions

- **Structure**: one module per concern, flat. Something like `vault.py`, `db.py`, `ingest.py`, `adapters/`, `llm.py`, `build.py`, `graph.py`, `server.py`, `mcp.py`, `cli.py`. Do not create packages inside packages.
- **Type hints** on public functions. `dataclass` for the `Item`/`Turn` contract. No pydantic.
- **No classes for things that are functions.** An adapter is a generator function, not a class hierarchy.
- **Docstrings explain why, not what.** `# parse the file` is noise; `# the mapping tree branches on regenerated answers, so walk every node in time order` is worth writing.
- **Errors name the fix.** Not `KeyError: conversations.json` but `No conversations found in <path>. Modern exports shard them as conversations-000.json; pass --format chatgpt-shards to force.`
- **f-strings, pathlib, no os.path.**

## Testing

- `pytest`. Fixtures in `tests/fixtures/`, synthetic, tiny.
- **No network in tests, ever.** The LLM client takes a `complete(system, user) -> str` callable so tests inject a fake. Do not mock `urllib`; inject the seam.
- What must have a test: every adapter (fixture in, expected item count and first item's fields out), the wikilink parser, the recursive-CTE graph queries, the page-block output parser, the slug validator, the trivia filter, and the compression function.
- What does not need a test: the CLI's argument plumbing, the HTML file.
- One command must run everything: `pytest -q`.

## Verification, not assumption

- After building a phase, **run it against real input** and paste the actual numbers into the phase's checkpoint in `PLAN.md`. "3,138 conversations ingested in 47s, 0 errors" is a checkpoint; "ingest works" is not.
- The owner's real export path is on their machine, not here. Ask them to run the command and share output rather than inventing numbers.
- **Never write invented data into docs, fixtures, or example output.** If you have not measured it, say you have not measured it.

## Docs discipline

The docs are a deliverable, not an afterthought — the whole point is adoption.

- `README.md`: hero GIF, one-line pitch, MCP config block within the first screenful, quickstart (three commands), the tested-provider table, "how it works" in five bullets, and a **"Not built" section** listing the deliberate omissions with reasons. Keep it under ~150 lines; link out for depth.
- `docs/`: one file per concern — `adapters.md` (with the worked 30-line example), `configuration.md`, `mcp.md`, `graph.md` (the recursive-CTE explanation, this one is blog-worthy), `costs.md`.
- `CONTRIBUTING.md`: leads with "add an adapter", because that is the contribution you want.
- Every doc claim must be true of the code as committed. If you change behaviour, update the doc in the same commit.

## Commits

- Small, one concern each. Present tense subject under ~70 chars, body explaining why when it is not obvious.
- Do not commit on `main` without being asked; branch and let the owner review.
- Do not push unless asked.

## When you disagree with this file

Say so in one or two sentences, then follow it anyway unless the owner agrees. If a rule is genuinely blocking correct behaviour — for instance, if a hard rule would force you to ship something broken — stop and ask rather than silently working around it.
