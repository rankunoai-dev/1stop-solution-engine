"""AnswerLLMTool — wires an LLMProvider to the persisted spend guard (R0.10).

Responsibilities
----------------
1. Estimate the call cost and ``reserve()`` against the day/month cap.
2. Stream the full response from the provider (any ``LLMProvider`` adapter).
3. ``record()`` the actual token counts and cost in ``llm_calls``.
4. On provider failure (``IntegrationError``): record a zero-cost failure row
   and re-raise so the caller can surface the error.

The tool is **not** a ``BaseTool`` subclass because ``BaseTool.execute`` is
synchronous and takes only a payload, while ``AnswerLLMTool.execute`` is async
and manages its own database connection.  The metadata class variable follows
the same convention so tooling and documentation can introspect it uniformly.

Typical usage::

    guard = PersistedSpendGuard.from_settings()
    tool = AnswerLLMTool(provider=OllamaAdapter("llama3.2"), guard=guard)

    async with transaction() as conn:
        result = await tool.execute(AnswerRequest(messages=[...]), conn)
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar

from sqlalchemy.ext.asyncio import AsyncConnection

from src.core.errors import IntegrationError
from src.core.schemas import RiskClass, ToolMetadata
from src.integrations.llm.base import LLMProvider, Message
from src.integrations.llm.pricing import cost_usd
from src.modules.platform.spend import PersistedSpendGuard

__all__ = ["AnswerLLMTool", "AnswerRequest", "AnswerResult"]


@dataclass
class AnswerRequest:
    """Input for a single LLM answer call."""

    messages: list[Message]
    max_tokens: int = 1024
    temperature: float = 0.7
    purpose: str = "answer"
    provider_name: str = "ollama"
    model_name: str = "llama3.2"


@dataclass
class AnswerResult:
    """Output of a successful LLM answer call."""

    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


class AnswerLLMTool:
    """Stream an LLM answer and record the cost against the spend guard.

    Args:
        provider: Any adapter implementing ``LLMProvider``.
        guard: Spend guard that enforces day/month caps and records calls.
    """

    metadata: ClassVar[ToolMetadata] = ToolMetadata(
        name="answer_llm",
        version="1.0.0",
        risk_class=RiskClass.FINANCIAL,
        summary="Streams an LLM answer and records the cost.",
    )

    def __init__(self, provider: LLMProvider, guard: PersistedSpendGuard) -> None:
        """Initialise with a provider and a spend guard."""
        self._provider = provider
        self._guard = guard

    async def execute(
        self,
        request: AnswerRequest,
        conn: AsyncConnection,
    ) -> AnswerResult:
        """Run the governed LLM call within the caller's transaction.

        Steps:

        1. Estimate token count and compute worst-case cost (max_tokens output).
        2. ``guard.reserve()`` — acquires advisory lock, checks caps.
        3. Stream the response, collecting all deltas.
        4. ``guard.record()`` — inserts the ``llm_calls`` row with actual counts.
        5. Return ``AnswerResult``.

        On ``CapExceededError``: propagates immediately (no record inserted).
        On ``IntegrationError``: records a zero-cost failure row, then re-raises.

        Args:
            request: Fully-formed answer request with messages and parameters.
            conn: Open ``AsyncConnection`` inside an active transaction.

        Returns:
            AnswerResult with the full text and token accounting.

        Raises:
            CapExceededError: Day/month cap exceeded or kill switch active.
            IntegrationError: Provider failed; failure row recorded.
        """
        # Step 1: estimate cost (worst case: max_tokens output tokens).
        input_est = await self._provider.count_tokens(request.messages)
        cost_est = cost_usd(
            request.provider_name,
            request.model_name,
            input_est,
            request.max_tokens,
        )

        # Step 2: reserve against the cap (raises CapExceededError if over).
        await self._guard.reserve(conn, cost_est)

        # Steps 3–4: stream, then record.
        try:
            full_text = ""
            async for delta in self._provider.stream(
                request.messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            ):
                full_text += delta.text

            usage = await self._provider.get_usage()

            await self._guard.record(
                conn,
                purpose=request.purpose,
                provider=request.provider_name,
                model=request.model_name,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost=usage.cost_usd,
            )

            return AnswerResult(
                text=full_text,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=usage.cost_usd,
            )

        except IntegrationError:
            # Record a zero-cost failure row so the call is auditable.
            await self._guard.record(
                conn,
                purpose=request.purpose,
                provider=request.provider_name,
                model=request.model_name,
                input_tokens=0,
                output_tokens=0,
                cost=Decimal("0"),
                status="failed",
            )
            raise
