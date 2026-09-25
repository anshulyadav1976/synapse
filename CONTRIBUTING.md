# Contributing

## Add an adapter

The most useful first contribution is support for one more text source. An adapter is usually one reader function, one registry import, and one tiny synthetic fixture. Start with the worked [30-line adapter guide](docs/adapters.md).

Good adapter pull requests:

- stream `Item` objects without touching storage or the model layer;
- preserve real boundaries, timestamps, and speaker names;
- use a stable source ID so reruns skip existing items;
- detect only signatures that will not steal another format's files;
- fall back gracefully for malformed records when useful data remains;
- include no personal export data, even anonymised excerpts from a real archive.

Formats currently wanted include WhatsApp, email (`.mbox`/`.eml`), Gemini, Discord, Slack, iMessage, Signal, Notion, Bear, and Apple Notes.

## Development

Synapse supports Python 3.11–3.13 and has zero runtime dependencies.

```bash
git clone https://github.com/anshulyadav1976/synapse.git
cd synapse
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest -q
ruff check .
```

Keep changes small and standard-library-first. Do not add a runtime dependency without discussing why the existing zero-dependency promise is no longer worth keeping.

## Data and security

Never commit a real conversation, mail, note, vault, API key, path containing a private identifier, or output derived from personal data. Fixtures must be tiny and wholly invented. Imported content is untrusted input: parsers store it, but must never execute or follow it.

## Pull requests

Explain the user-visible behavior, show the command you ran, and include measured output when claiming speed, cost, or scale. Update docs when the command or data contract changes.
