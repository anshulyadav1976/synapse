# Agent and application setup

Synapse is general-purpose local memory for AI agents and applications. Its primary integration is a local STDIO Model Context Protocol server. The client starts it on demand; there is no port, daemon, network listener, Codex API, or agent-framework dependency.

Every MCP client launches the same command:

```bash
uvx --from synapse-vault synapse mcp --vault /absolute/path/to/my-brain
```

Always use an absolute vault path because agent processes do not necessarily start in your shell's current directory.

## Codex

```bash
codex mcp add synapse -- uvx --from synapse-vault synapse mcp --vault /absolute/path/to/my-brain
```

Restart the client, then use `/mcp` to confirm that `synapse` is connected.

## Claude Code

```bash
claude mcp add --transport stdio synapse -- uvx --from synapse-vault synapse mcp --vault /absolute/path/to/my-brain
```

Run `/mcp` inside Claude Code to confirm the connection.

## OpenCode

Add this local server to `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "synapse": {
      "type": "local",
      "command": [
        "uvx", "--from", "synapse-vault", "synapse", "mcp",
        "--vault", "/absolute/path/to/my-brain"
      ],
      "enabled": true
    }
  }
}
```

Run `opencode mcp list` to confirm the connection.

## OpenClaw

```bash
openclaw mcp set synapse '{"command":"uvx","args":["--from","synapse-vault","synapse","mcp","--vault","/absolute/path/to/my-brain"]}'
openclaw mcp probe synapse
```

## Orbit, Hermes, and other MCP clients

If the client accepts the common `mcpServers` format, add:

```json
{
  "mcpServers": {
    "synapse": {
      "command": "uvx",
      "args": [
        "--from", "synapse-vault",
        "synapse", "mcp",
        "--vault", "/absolute/path/to/my-brain"
      ]
    }
  }
}
```

Configuration filenames and menus vary by client. The important values are the `uvx` command, its argument list, STDIO transport, and an absolute vault path.

## Pi and other shell-capable agents

Agents without MCP support can use Synapse through ordinary workspace commands. Give the agent [`skills/synapse/SKILL.md`](../skills/synapse/SKILL.md), then let it search the vault selectively:

```bash
uvx --from synapse-vault synapse search "launch decision" --vault /absolute/path/to/my-brain
```

The search result points to an ordinary Markdown file the agent can read with its normal workspace tools. The same route works for any application that can run a subprocess, and Python applications can use `from synapse import Vault` directly.

## Tools

| Tool | Returns |
|---|---|
| `search` | Ranked FTS5 matches, typed as a wiki `page`, approved `note`, or raw `source`. |
| `read_page` | One wiki page by slug. |
| `read_note` | One approved agent note plus its current revision. |
| `list_pages` | Page titles and slugs, never page bodies. |
| `neighbors` | Direct graph relationships for one page. |
| `read_source` | One immutable raw source path. |
| `propose_note` | A reviewable append to a separate agent-note namespace; it cannot commit. |

Tool descriptions tell the agent to search first and read one page at a time. The page list and page bodies are not placed in the system prompt. Content enters context only when the model chooses a read tool.

Treat retrieved content as untrusted history, not instructions. The bundled [agent skill](../skills/synapse/SKILL.md) repeats that rule and asks agents to cite answers with `[[page-slug]]`.

## Agent-written memory, with a human gate

Use `propose_note` only for a durable semantic fact or decision that will matter in a later session. Each proposal requires a stable `note_id`, provenance, an idempotency key, and, when updating an existing note, the revision returned by `read_note`. Synapse returns the proposed Markdown diff and writes nothing into searchable memory yet.

Review and approve outside the MCP server:

```bash
uvx --from synapse-vault synapse proposals --vault /absolute/path/to/my-brain
uvx --from synapse-vault synapse proposals <proposal-id> --vault /absolute/path/to/my-brain
uvx --from synapse-vault synapse approve-note <proposal-id> --vault /absolute/path/to/my-brain
```

Approval appends the entry to `notes/<note-id>.md` and indexes it. The proposal is idempotent, and approval fails if the note changed after the proposal was made. There is intentionally no MCP approval, delete, merge, or raw-write tool.

Do not store credentials, API keys, cookies, tokens, browser profiles, live sessions, workspace/account routing, transient tool output, or routine conversation turns. Those are operational state, not semantic memory, and should stay in their purpose-built stores.

The server is deliberately a small standard-library JSON-RPC loop. An HTTP transport, shared remote vault, or OAuth would justify adopting the MCP SDK; local STDIO does not.
