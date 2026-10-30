"""Anthropic Messages API and OpenAI-compatible Chat Completions clients (httpx).

10-second timeout and one retry. Any failure raises ``ProviderError``; callers continue
without a guide. The key is only ever sent to the configured endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx

TIMEOUT = 10.0
RETRIES = 1
ANTHROPIC_URL = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"
OPENAI_URL = "https://api.openai.com/v1"
DEFAULT_MODELS = {"anthropic": "claude-haiku-5-5", "openai-compatible": "gpt-4o-mini"}


class ProviderError(Exception):
    pass


class Provider(Protocol):
    model: str

    def complete(self, system: str, user: str) -> str: ...


def _post(url: str, headers: dict[str, str], body: dict[str, Any],
          transport: httpx.BaseTransport | None) -> dict[str, Any]:
    last: Exception | None = None
    for _ in range(RETRIES + 1):
        try:
            with httpx.Client(timeout=TIMEOUT, transport=transport) as client:
                resp = client.post(url, headers=headers, json=body)
            if resp.status_code >= 500 or resp.status_code == 429:
                last = ProviderError(f"HTTP {resp.status_code}")
                continue
            if resp.status_code >= 400:
                raise ProviderError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            if not isinstance(data, dict):
                raise ProviderError("unexpected response")
            return data
        except (httpx.HTTPError, ValueError) as exc:
            last = exc
    raise ProviderError(str(last) if last else "request failed")


@dataclass
class Anthropic:
    api_key: str
    model: str = DEFAULT_MODELS["anthropic"]
    endpoint: str = ANTHROPIC_URL
    transport: httpx.BaseTransport | None = None

    def complete(self, system: str, user: str) -> str:
        base = (self.endpoint or ANTHROPIC_URL).rstrip("/")
        url = base if base.endswith("/messages") else f"{base}/v1/messages"
        data = _post(
            url,
            {"x-api-key": self.api_key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"},
            {"model": self.model, "max_tokens": 300, "system": system,
             "messages": [{"role": "user", "content": user}]},
            self.transport,
        )
        parts = [b.get("text", "") for b in data.get("content", []) if isinstance(b, dict) and b.get("type") == "text"]
        text = "".join(parts).strip()
        if not text:
            raise ProviderError("empty response")
        return text


@dataclass
class OpenAICompatible:
    api_key: str
    model: str = DEFAULT_MODELS["openai-compatible"]
    endpoint: str = OPENAI_URL
    transport: httpx.BaseTransport | None = None

    def complete(self, system: str, user: str) -> str:
        base = (self.endpoint or OPENAI_URL).rstrip("/")
        url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        data = _post(
            url, headers,
            {"model": self.model, "max_tokens": 300, "temperature": 0.2,
             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            self.transport,
        )
        try:
            text = str(data["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("unexpected response") from exc
        if not text:
            raise ProviderError("empty response")
        return text


def make_provider(name: str, api_key: str, model: str = "", endpoint: str = "",
                  transport: httpx.BaseTransport | None = None) -> Provider | None:
    if name == "anthropic":
        if not api_key:
            return None
        return Anthropic(api_key=api_key, model=model or DEFAULT_MODELS["anthropic"],
                         endpoint=endpoint or ANTHROPIC_URL, transport=transport)
    if name == "openai-compatible":
        # Local servers such as Ollama need no key.
        if not api_key and not endpoint:
            return None
        return OpenAICompatible(api_key=api_key, model=model or DEFAULT_MODELS["openai-compatible"],
                                endpoint=endpoint or OPENAI_URL, transport=transport)
    return None
