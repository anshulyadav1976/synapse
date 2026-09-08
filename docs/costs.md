# Costs and control

Ingest, search, reindex, graph browsing, the dashboard demo, and MCP retrieval make no model calls. Only `build` and `ask` call the configured OpenAI-compatible endpoint.

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

For offline use, point Synapse at an OpenAI-compatible local model in Ollama or LM Studio. Local inference has no API bill, though its speed and output quality depend on the model and machine.
