"""One dependency-free POST to any OpenAI-compatible endpoint."""

import json
import math
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


class OpenAICompatible:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 90,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.usage = Usage()

    def complete(self, system: str, user: str) -> str:
        payload = self._post(
            "chat/completions",
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        self._record_usage(payload)
        try:
            content = payload["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
            return str(content)
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise RuntimeError(
                f"LLM endpoint {self.base_url} returned an invalid chat completion response"
            ) from error

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch without coupling Synapse to an SDK."""
        if not texts:
            return []
        payload = self._post("embeddings", {"model": self.model, "input": texts})
        self._record_usage(payload)
        try:
            data = sorted(payload["data"], key=lambda item: int(item["index"]))
            vectors = [[float(value) for value in item["embedding"]] for item in data]
            if len(vectors) != len(texts) or any(
                not vector or not all(math.isfinite(value) for value in vector)
                for vector in vectors
            ):
                raise ValueError("invalid embedding batch")
            return vectors
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise RuntimeError(
                f"LLM endpoint {self.base_url} returned an invalid embeddings response"
            ) from error

    def _record_usage(self, payload: dict[str, object]) -> None:
        usage = payload.get("usage") or {}
        if not isinstance(usage, dict):
            return
        self.usage.input_tokens += int(
            usage.get("prompt_tokens", usage.get("input_tokens", usage.get("total_tokens", 0)))
            or 0
        )
        self.usage.output_tokens += int(
            usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0
        )

    def _post(self, route: str, payload: dict[str, object]) -> dict[str, object]:
        body = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        endpoint = f"{self.base_url}/{route}"
        request = Request(endpoint, data=body, headers=headers, method="POST")

        for attempt in range(2):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    payload = json.load(response)
                if not isinstance(payload, dict):
                    raise TypeError("response must be an object")
                return payload
            except HTTPError as error:
                if (error.code == 429 or error.code >= 500) and attempt == 0:
                    time.sleep(1)
                    continue
                if error.code in {401, 403}:
                    key = (
                        "SYNAPSE_EMBEDDING_API_KEY or SYNAPSE_API_KEY"
                        if route == "embeddings"
                        else "SYNAPSE_API_KEY"
                    )
                    raise RuntimeError(
                        f"Authentication failed at {self.base_url}. Check {key}."
                    ) from error
                detail = error.read(500).decode(errors="replace")
                raise RuntimeError(
                    f"LLM request to {self.base_url} failed with HTTP {error.code}: {detail}"
                ) from error
            except (URLError, TimeoutError) as error:
                if attempt == 0:
                    time.sleep(1)
                    continue
                raise RuntimeError(f"Could not reach LLM endpoint {self.base_url}: {error}") from error
            except (TypeError, ValueError) as error:
                raise RuntimeError(
                    f"LLM endpoint {self.base_url} returned invalid JSON"
                ) from error
        raise AssertionError("retry loop exited unexpectedly")
