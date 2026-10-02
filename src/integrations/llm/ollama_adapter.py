"""OllamaAdapter — LLMProvider backed by Ollama's OpenAI-compatible HTTP API.

Ollama exposes a streaming chat endpoint at ``POST /api/chat`` that returns
newline-delimited JSON (NDJSON).  Non-final lines carry a ``message.content``
field; the final line has ``done=true`` with ``eval_count`` (output tokens) and
``prompt_eval_count`` (input tokens).

Ollama is free to run locally, so ``cost_usd`` is always ``Decimal("0")``
(see ``pricing.cost_usd``).

Example::

    adapter = OllamaAdapter(model="llama3.2")
    async for delta in adapter.stream([Message(role="user", content="Hi")]):
        print(delta.text, end="", flush=True)
    usage = await adapter.get_usage()
    # usage.cost_usd == Decimal("0")
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from src.core.errors import IntegrationError
from src.integrations.llm.base import Delta, Message, Usage
from src.integrations.llm.pricing import cost_usd

__all__ = ["OllamaAdapter"]


class OllamaAdapter:
    """LLMProvider that streams from a local Ollama instance via NDJSON.

    Args:
        model: Ollama model tag, e.g. ``"llama3.2"`` or ``"mistral"``.
        base_url: Root URL of the Ollama server.  Defaults to the Ollama
            default of ``http://localhost:11434``.
    """

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
    ) -> None:
        """Initialise the adapter with a model tag and optional base URL."""
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._input_tokens: int = 0
        self._output_tokens: int = 0

    # ------------------------------------------------------------------
    # LLMProvider interface
    # ------------------------------------------------------------------

    async def stream(
        self,
        messages: list[Message],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> AsyncGenerator[Delta, None]:
        """Stream token deltas from Ollama.

        Yields ``Delta`` objects for each non-final NDJSON line.  The final
        ``done=true`` line is consumed silently and its token counts are stored
        for ``get_usage()``.

        Args:
            messages: Conversation history to pass to the model.
            max_tokens: Maximum number of tokens to generate.
            temperature: Sampling temperature (0 = deterministic, 1 = creative).

        Yields:
            Delta: Each streamed text chunk from the model.

        Raises:
            IntegrationError: On HTTP error (4xx/5xx) or malformed JSON line.
        """
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        url = f"{self._base_url}/api/chat"

        try:
            async with (
                httpx.AsyncClient() as client,
                client.stream("POST", url, json=payload) as response,
            ):
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise IntegrationError("ollama", str(exc)) from exc

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk: dict[str, Any] = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise IntegrationError("ollama", f"JSON decode error: {exc}") from exc

                    if chunk.get("done"):
                        self._input_tokens = int(chunk.get("prompt_eval_count") or 0)
                        self._output_tokens = int(chunk.get("eval_count") or 0)
                    else:
                        content = str((chunk.get("message") or {}).get("content") or "")
                        yield Delta(text=content)

        except IntegrationError:
            raise
        except (httpx.RequestError, OSError) as exc:
            raise IntegrationError("ollama", str(exc)) from exc

    async def count_tokens(self, messages: list[Message]) -> int:
        """Estimate input token count using a word-count heuristic.

        Uses the formula ``word_count × 4 // 3`` (approximately 1.3 tokens
        per word) to avoid making a round-trip to Ollama just for estimation.
        Exact counts are captured from the streaming response and available
        via ``get_usage()`` after the stream completes.

        Args:
            messages: Messages whose combined token count to estimate.

        Returns:
            Estimated token count (integer; may be 0 for empty messages).
        """
        return sum(len(m.content.split()) * 4 // 3 for m in messages)

    async def get_usage(self) -> Usage:
        """Return usage captured from the most recent ``stream()`` call.

        Token counts come from the ``done=true`` NDJSON line.  Before any
        stream has been consumed, both counts are 0.  Ollama is free to run
        locally, so ``cost_usd`` is always ``Decimal("0")``.

        Returns:
            Usage with token counts and zero cost.
        """
        return Usage(
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            cost_usd=cost_usd("ollama", self._model, self._input_tokens, self._output_tokens),
        )
