"""Local-only dashboard and REST API using the Python standard library."""

import json
import shutil
import tempfile
import threading
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, urlparse

from .build import actual_cost, build, estimate, valid_slug
from .db import connect
from .graph import graph_json
from .index import index_document, reindex, replace_links
from .ingest import ingest
from .llm import OpenAICompatible
from .vault import Vault


class Dashboard:
    def __init__(self, vault: Vault) -> None:
        self.vault = vault
        self.jobs: dict[str, dict[str, object]] = {}
        self.lock = threading.Lock()
        self.html = files("synapse").joinpath("dashboard.html").read_text(encoding="utf-8")

    def get(self, path: str, query: dict[str, list[str]]) -> object:
        if path == "/api/status":
            return self.vault.status()
        if path == "/api/search":
            return self.vault.search(_one(query, "q"), int(_one(query, "limit", "20")))
        if path == "/api/graph":
            return graph_json(self.vault)
        if path == "/api/page":
            slug = _one(query, "slug")
            page = self._page(slug)
            return {"slug": slug, "markdown": page.read_text(encoding="utf-8")}
        if path == "/api/source":
            relative = _safe_source(_one(query, "path"))
            source = self.vault.path / relative
            if not source.is_file():
                raise FileNotFoundError(f"Source not found: {relative}")
            return {"path": relative.as_posix(), "markdown": source.read_text(encoding="utf-8")}
        if path == "/api/job":
            job_id = _one(query, "id")
            with self.lock:
                if job_id not in self.jobs:
                    raise FileNotFoundError(f"Job not found: {job_id}")
                return dict(self.jobs[job_id])
        raise FileNotFoundError(f"Unknown endpoint: {path}")

    def write_page(self, payload: dict[str, object]) -> object:
        slug = str(payload.get("slug", ""))
        markdown = str(payload.get("markdown", ""))
        if not markdown.startswith("# "):
            raise ValueError("A page must start with a Markdown heading")
        page = self._page(slug)
        page.write_text(markdown.rstrip() + "\n", encoding="utf-8")
        with connect(self.vault.db_path) as connection:
            title = markdown.splitlines()[0].removeprefix("# ").strip()
            index_document(connection, f"wiki/{slug}.md", title, markdown)
            replace_links(connection, slug, markdown)
        return {"saved": slug}

    def start_ingest(self, payload: dict[str, object]) -> object:
        input_path = str(payload.get("path", ""))
        if not input_path:
            raise ValueError("Choose a file or folder to ingest")

        def work(job_id: str) -> dict[str, object]:
            result = ingest(
                self.vault,
                input_path,
                str(payload["format"]) if payload.get("format") else None,
                int(payload.get("min_chars", 200)),
                self.vault.config().owner,
                lambda current: self._progress(
                    job_id,
                    f"Seen {current.seen} · added {current.added} · skipped {current.skipped + current.filtered}",
                ),
            )
            return {
                "seen": result.seen,
                "added": result.added,
                "skipped": result.skipped + result.filtered,
                "api_calls": 0,
            }

        return self._job("ingest", work)

    def start_build(self, payload: dict[str, object]) -> object:
        config = self.vault.config()
        limit_value = payload.get("limit")
        limit = int(limit_value) if limit_value not in {None, ""} else None
        quote = estimate(self.vault, config, limit, bool(payload.get("oldest", False)))
        if payload.get("dry_run"):
            return {"estimate": quote.__dict__, "api_calls": 0}
        if quote.input_tokens > 200_000 and not payload.get("confirmed"):
            raise ValueError("This build exceeds 200,000 input tokens; confirm the estimate first")
        if not config.api_key and not config.base_url.startswith(
            ("http://localhost", "http://127.0.0.1")
        ):
            raise ValueError("Configure an API key in synapse.toml before building")

        def work(job_id: str) -> dict[str, object]:
            client = OpenAICompatible(config.base_url, config.api_key, config.model)
            result = build(
                self.vault,
                config,
                client.complete,
                limit,
                bool(payload.get("oldest", False)),
                lambda current: self._progress(
                    job_id, f"Built {current.items} item(s) · wrote {current.pages} page(s)"
                ),
            )
            return {
                "items": result.items,
                "pages": result.pages,
                "input_tokens": client.usage.input_tokens,
                "output_tokens": client.usage.output_tokens,
                "cost": actual_cost(
                    config, client.usage.input_tokens, client.usage.output_tokens
                ),
            }

        return self._job("build", work)

    def _page(self, slug: str) -> Path:
        if not valid_slug(slug):
            raise ValueError("Invalid page slug")
        page = self.vault.wiki_path / f"{slug}.md"
        if not page.is_file():
            raise FileNotFoundError(f"Page not found: {slug}")
        return page

    def _job(self, kind: str, work) -> dict[str, str]:
        job_id = uuid.uuid4().hex
        with self.lock:
            self.jobs[job_id] = {"id": job_id, "kind": kind, "state": "running", "message": "Starting…"}

        def run() -> None:
            try:
                result = work(job_id)
                with self.lock:
                    self.jobs[job_id].update(state="complete", message="Complete", result=result)
            except Exception as error:  # noqa: BLE001 - background failures become job state
                with self.lock:
                    self.jobs[job_id].update(state="failed", message=str(error))

        threading.Thread(target=run, daemon=True).start()
        return {"job_id": job_id}

    def _progress(self, job_id: str, message: str) -> None:
        with self.lock:
            self.jobs[job_id]["message"] = message


def _one(query: dict[str, list[str]], name: str, default: str = "") -> str:
    return query.get(name, [default])[0]


def _safe_source(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or not path.parts or path.parts[0] != "raw" or ".." in path.parts:
        raise ValueError("Source paths must stay inside raw/")
    return path


def handler(app: Dashboard) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send(app.html, "text/html; charset=utf-8")
                return
            try:
                self._json(app.get(parsed.path, parse_qs(parsed.query)))
            except Exception as error:  # noqa: BLE001 - HTTP boundary returns JSON errors
                self._error(error)

        def do_POST(self) -> None:
            try:
                payload = self._payload()
                if self.path == "/api/ingest":
                    self._json(app.start_ingest(payload), HTTPStatus.ACCEPTED)
                elif self.path == "/api/build":
                    self._json(app.start_build(payload), HTTPStatus.ACCEPTED)
                else:
                    raise FileNotFoundError(f"Unknown endpoint: {self.path}")
            except Exception as error:  # noqa: BLE001 - HTTP boundary returns JSON errors
                self._error(error)

        def do_PUT(self) -> None:
            try:
                if self.path != "/api/page":
                    raise FileNotFoundError(f"Unknown endpoint: {self.path}")
                self._json(app.write_page(self._payload()))
            except Exception as error:  # noqa: BLE001 - HTTP boundary returns JSON errors
                self._error(error)

        def _payload(self) -> dict[str, object]:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length) or b"{}")

        def _json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
            self._send(
                json.dumps(payload, ensure_ascii=False).encode(),
                "application/json; charset=utf-8",
                status,
            )

        def _send(
            self,
            payload: str | bytes,
            content_type: str,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            body = payload.encode() if isinstance(payload, str) else payload
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _error(self, error: Exception) -> None:
            status = HTTPStatus.NOT_FOUND if isinstance(error, FileNotFoundError) else HTTPStatus.BAD_REQUEST
            self._json({"error": str(error)}, status)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def demo_vault() -> tuple[Vault, tempfile.TemporaryDirectory[str]]:
    temporary = tempfile.TemporaryDirectory(prefix="synapse-demo-")
    source = files("synapse").joinpath("demo")
    shutil.copytree(str(source), temporary.name, dirs_exist_ok=True)
    vault = Vault(temporary.name)
    vault.init()
    reindex(vault.path)
    return vault, temporary


def serve(vault: Vault, port: int = 8765, open_browser: bool = True) -> None:
    address = ("127.0.0.1", port)
    server = ThreadingHTTPServer(address, handler(Dashboard(vault)))
    url = f"http://127.0.0.1:{port}"
    print(f"Synapse is running at {url}", flush=True)
    print(f"Vault: {vault.path}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
