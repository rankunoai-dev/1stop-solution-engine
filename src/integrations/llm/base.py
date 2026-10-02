"""LLM provider abstraction — Protocol and data models (R0.10).

Every LLM adapter in the integrations layer must satisfy the ``LLMProvider``
Protocol.  Callers in ``src.modules`` depend only on this interface, so
adapters can be swapped without changing any module-layer code.

Typical streaming usage::

    async for delta in provider.stream(messages, max_tokens=512):
        full_text += delta.text

    usage = await provider.get_usage()
    # usage.cost_usd is Decimal("0") for Ollama, non-zero for paid providers.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol, runtime_checkable

__all__ = ["Delta", "LLMProvider", "Message", "Usage"]


@dataclass
class Message:
    """A single message in an LLM conversation."""

    role: Literal["user", "assistant", "system"]
    content: str


@dataclass
class Delta:
    """One streamed token chunk from an LLM response."""

    text: str


@dataclass
class Usage:
    """Token counts and computed cost for a completed LLM call."""

    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


@runtime_checkable
class LLMProvider(Protocol):
    """Structural interface every LLM adapter must satisfy.

    Calling ``stream()`` returns an ``AsyncGenerator`` that yields ``Delta``
    objects; no ``await`` is needed at the call site::

        async for delta in provider.stream(messages):
            text += delta.text

    After consuming the generator, call ``get_usage()`` to read the token
    counts and cost captured from the final response line.
    """

    def stream(
        self,
        messages: list[Message],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> AsyncGenerator[Delta, None]:
        """Yield token deltas; raise ``IntegrationError`` on transport failure."""
        ...

    async def count_tokens(self, messages: list[Message]) -> int:
        """Estimate input token count without making a call."""
        ...

    async def get_usage(self) -> Usage:
        """Return usage from the most recent ``stream()`` call."""
        ...
