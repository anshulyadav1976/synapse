"""One dependency-free POST to any OpenAI-compatible endpoint."""

import json
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
        body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        ).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        endpoint = f"{self.base_url}/chat/completions"
        request = Request(endpoint, data=body, headers=headers, method="POST")

        for attempt in range(2):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    payload = json.load(response)
                usage = payload.get("usage") or {}
                self.usage.input_tokens += int(
                    usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0
                )
                self.usage.output_tokens += int(
                    usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0
                )
                content = payload["choices"][0]["message"]["content"]
                if isinstance(content, list):
                    content = "".join(
                        part.get("text", "") for part in content if isinstance(part, dict)
                    )
                return str(content)
            except HTTPError as error:
                if (error.code == 429 or error.code >= 500) and attempt == 0:
                    time.sleep(1)
                    continue
                if error.code in {401, 403}:
                    raise RuntimeError(
                        f"Authentication failed at {self.base_url}. Check SYNAPSE_API_KEY."
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
            except (KeyError, IndexError, TypeError, ValueError) as error:
                raise RuntimeError(
                    f"LLM endpoint {self.base_url} returned an invalid chat completion response"
                ) from error
        raise AssertionError("retry loop exited unexpectedly")
