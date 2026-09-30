# Configuration

Every command that reads a vault accepts `--vault`. The default is `./synapse-vault`, keeping the personal data visible and project-scoped. Set `SYNAPSE_VAULT` to change that default. `synapse init PATH` creates `synapse.toml` there.

```toml
owner = "Your name, me"
base_url = "https://api.openai.com/v1"
model = "gpt-4o-mini"
embedding_model = "text-embedding-3-small"
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
| `SYNAPSE_EMBEDDING_BASE_URL` | Optional embedding API root; defaults to `SYNAPSE_BASE_URL`. |
| `SYNAPSE_EMBEDDING_API_KEY` | Optional embedding key; defaults to `SYNAPSE_API_KEY`. |
| `SYNAPSE_EMBEDDING_MODEL` | Model sent to `/embeddings`; defaults to `text-embedding-3-small`. |
| `SYNAPSE_OWNER` | Comma-separated names that identify the owner in conversations. |
| `SYNAPSE_INPUT_COST_PER_MILLION` | Input-token price used only for estimates. |
| `SYNAPSE_OUTPUT_COST_PER_MILLION` | Output-token price used only for estimates. |

For a local server, no API key is required:

```bash
SYNAPSE_BASE_URL=http://localhost:11434/v1 \
SYNAPSE_MODEL=qwen3:8b \
uvx --from synapse-vault synapse build --vault ./my-brain --limit 5
```

Synapse sends conventional chat-completions and embeddings requests. It retries one transient `429` or `5xx` and names the failing base URL in connection errors. Ingest, keyword search, graph browsing, `build --dry-run`, and `embed --dry-run` send nothing.

The dashboard displays and searches the vault, but it does not collect or persist secrets. Set keys in the process environment before starting `synapse serve`, or add `api_key` / `embedding_api_key` to the local `synapse.toml` if you accept plaintext local storage. There is intentionally no browser key form.

Do not commit `synapse.toml` if you place a credential in it. A local environment variable or secret manager is safer.
