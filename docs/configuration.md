# Configuration

Every command that reads a vault accepts `--vault`. The default is `./synapse-vault`, keeping the personal data visible and project-scoped. Set `SYNAPSE_VAULT` to change that default. `synapse init PATH` creates `synapse.toml` there.

```toml
owner = "Your name, me"
base_url = "https://api.openai.com/v1"
model = "gpt-4o-mini"
input_cost_per_million = 0.15
output_cost_per_million = 0.60
```

Environment variables override the file:

| Variable | Purpose |
|---|---|
| `SYNAPSE_VAULT` | Default vault path when `--vault` is omitted. |
| `SYNAPSE_API_KEY` | Provider key. Prefer this to storing a key in a vault. |
| `SYNAPSE_BASE_URL` | OpenAI-compatible API root, ending in `/v1`. |
| `SYNAPSE_MODEL` | Model name sent to `/chat/completions`. |
| `SYNAPSE_OWNER` | Comma-separated names that identify the owner in conversations. |
| `SYNAPSE_INPUT_COST_PER_MILLION` | Input-token price used only for estimates. |
| `SYNAPSE_OUTPUT_COST_PER_MILLION` | Output-token price used only for estimates. |

For a local server, no API key is required:

```bash
SYNAPSE_BASE_URL=http://localhost:11434/v1 \
SYNAPSE_MODEL=qwen3:8b \
uvx --from synapse-vault synapse build --vault ./my-brain --limit 5
```

Synapse sends a conventional chat-completions request. It retries one transient `429` or `5xx`, names the failing base URL in connection errors, and does not send anything during ingest, search, graph browsing, or `build --dry-run`.

Do not commit `synapse.toml` if you place a credential in it. A local environment variable or secret manager is safer.
