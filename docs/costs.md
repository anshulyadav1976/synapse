# Costs and control

Ingest, keyword search, reindex, graph browsing, and the dashboard demo make no model calls. `build` and `ask` call the configured chat endpoint. `embed` builds the optional semantic cache, and each hybrid query embeds its query text.

Before building, print an estimate without sending data:

```bash
uvx --from synapse-vault synapse build --vault ./my-brain --limit 20 --dry-run
```

The estimate uses the prompt size plus the prices in `synapse.toml`:

```text
cost = (input_tokens × input_price + output_tokens × output_price) / 1,000,000
```

Output is conservatively estimated at 1,200 tokens per source. Actual token counts reported by the provider are printed after a build or question.

One measured five-item OpenAI `gpt-4o-mini` verification used 8,216 input tokens and 3,383 output tokens, costing $0.0033 at the configured rates. That is an observed development run, not a promise: source length, existing wiki context, model, and provider prices all change the result.

Build is resumable. Each completed item receives a receipt, so another `--limit 20` continues with unbuilt items instead of paying again. Above 200,000 estimated input tokens, the CLI requires explicit confirmation; automation can pass `--yes` after inspecting a dry run.

`synapse embed --dry-run` reports documents, chunks, pending chunks, and estimated input tokens without making an API call. Only changed chunks are sent on the next run. Wiki pages and approved notes are the default scope; `--include-raw` is explicit because it can send substantially more private text. Provider prices vary, so Synapse reports tokens rather than inventing an embedding price.

For offline use, point Synapse at an OpenAI-compatible local model in Ollama or LM Studio. Local inference has no API bill, though its speed and output quality depend on the model and machine.
