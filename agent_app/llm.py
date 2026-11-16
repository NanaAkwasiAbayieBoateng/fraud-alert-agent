"""LLM clients.

Real runs use a local Ollama server over its HTTP API (free, no keys).
Tests use :class:`ScriptedFakeLLM`, which replays canned responses, so the
agent loop can be exercised end-to-end without Ollama running.
"""

from __future__ import annotations

import os
from typing import Callable, NamedTuple, Optional, Sequence, Union

import httpx


class ChatResult(NamedTuple):
    text: str
    tokens: int


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class OllamaChatClient:
    """Chat client for a local Ollama server.

    Model and host are configurable via the ``OLLAMA_MODEL`` and
    ``OLLAMA_HOST`` environment variables.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        host: Optional[str] = None,
        timeout: float = 120.0,
    ) -> None:
        self.model = model or os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
        self.host = (host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        self.timeout = timeout

    def chat(self, messages: Sequence[dict]) -> ChatResult:
        # trust_env=False: a local server must never be routed through a
        # proxy from the environment (and broken proxy values must not
        # stop us from reaching localhost).
        with httpx.Client(trust_env=False, timeout=self.timeout) as client:
            response = client.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": list(messages),
                    "stream": False,
                    "options": {"temperature": 0},
                },
            )
        response.raise_for_status()
        data = response.json()
        text = data["message"]["content"]
        tokens = int(data.get("prompt_eval_count", 0)) + int(data.get("eval_count", 0))
        if tokens == 0:
            tokens = _estimate_tokens(text)
        return ChatResult(text=text, tokens=tokens)


ScriptedResponse = Union[str, Callable[[Sequence[dict]], str]]


class ScriptedFakeLLM:
    """Deterministic stand-in for tests: replays scripted responses in order.

    Each scripted item is either a string or a callable that receives the
    message list and returns a string. Every call is recorded in ``calls``.
    """

    def __init__(self, responses: Sequence[ScriptedResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[list[dict]] = []

    def chat(self, messages: Sequence[dict]) -> ChatResult:
        self.calls.append([dict(m) for m in messages])
        if not self._responses:
            raise RuntimeError("ScriptedFakeLLM ran out of scripted responses")
        item = self._responses.pop(0)
        text = item(messages) if callable(item) else item
        return ChatResult(text=text, tokens=_estimate_tokens(text))
