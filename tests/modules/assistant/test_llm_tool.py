"""Tests for src.modules.assistant.llm_tool — AnswerLLMTool."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from src.core.errors import IntegrationError
from src.integrations.llm.base import Delta, Message, Usage
from src.modules.assistant.llm_tool import AnswerLLMTool, AnswerRequest, AnswerResult
from src.modules.platform.spend import CapExceededError, PersistedSpendGuard

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeProvider:
    """Configurable LLMProvider for unit tests."""

    def __init__(
        self,
        deltas: list[Delta],
        usage: Usage,
        raise_on_stream: Exception | None = None,
    ) -> None:
        self._deltas = deltas
        self._usage = usage
        self._raise_on_stream = raise_on_stream
        self.stream_calls: list[list[Message]] = []
        self.count_calls: list[list[Message]] = []
        self.usage_calls: int = 0

    async def stream(
        self,
        messages: list[Message],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> AsyncGenerator[Delta, None]:
        self.stream_calls.append(messages)
        if self._raise_on_stream is not None:
            raise self._raise_on_stream
        for delta in self._deltas:
            yield delta

    async def count_tokens(self, messages: list[Message]) -> int:
        self.count_calls.append(messages)
        return sum(len(m.content.split()) * 4 // 3 for m in messages)

    async def get_usage(self) -> Usage:
        self.usage_calls += 1
        return self._usage


def _make_guard() -> AsyncMock:
    """Mock guard with async reserve and record."""
    guard = AsyncMock(spec=PersistedSpendGuard)
    guard.reserve.return_value = None
    guard.record.return_value = uuid.uuid4()
    return guard


def _make_conn() -> AsyncMock:
    return AsyncMock(spec=AsyncConnection)


def _make_provider(
    texts: list[str] | None = None,
    input_tokens: int = 10,
    output_tokens: int = 5,
    raise_on_stream: Exception | None = None,
) -> FakeProvider:
    deltas = [Delta(text=t) for t in (["Hello", " world"] if texts is None else texts)]
    usage = Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=Decimal("0"),
    )
    return FakeProvider(deltas=deltas, usage=usage, raise_on_stream=raise_on_stream)


_MESSAGES = [Message(role="user", content="hi")]


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class TestMetadata:
    def test_metadata_name(self):
        from src.core.schemas import ToolMetadata

        assert isinstance(AnswerLLMTool.metadata, ToolMetadata)
        assert AnswerLLMTool.metadata.name == "answer_llm"

    def test_metadata_risk_class_financial(self):
        from src.core.schemas import RiskClass

        assert AnswerLLMTool.metadata.risk_class == RiskClass.FINANCIAL


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    async def test_returns_answer_result(self):
        provider = _make_provider(texts=["Hello", " world"])
        guard = _make_guard()
        tool = AnswerLLMTool(provider=provider, guard=guard)
        conn = _make_conn()
        result = await tool.execute(AnswerRequest(messages=_MESSAGES), conn)
        assert isinstance(result, AnswerResult)

    async def test_full_text_is_concatenation_of_deltas(self):
        provider = _make_provider(texts=["Hello", " world"])
        guard = _make_guard()
        tool = AnswerLLMTool(provider=provider, guard=guard)
        conn = _make_conn()
        result = await tool.execute(AnswerRequest(messages=_MESSAGES), conn)
        assert result.text == "Hello world"

    async def test_token_counts_from_usage(self):
        provider = _make_provider(input_tokens=20, output_tokens=8)
        guard = _make_guard()
        tool = AnswerLLMTool(provider=provider, guard=guard)
        conn = _make_conn()
        result = await tool.execute(AnswerRequest(messages=_MESSAGES), conn)
        assert result.input_tokens == 20
        assert result.output_tokens == 8

    async def test_cost_usd_from_usage(self):
        usage = Usage(input_tokens=10, output_tokens=5, cost_usd=Decimal("0.001"))
        provider = FakeProvider(deltas=[Delta(text="ok")], usage=usage)
        guard = _make_guard()
        tool = AnswerLLMTool(provider=provider, guard=guard)
        conn = _make_conn()
        result = await tool.execute(AnswerRequest(messages=_MESSAGES), conn)
        assert result.cost_usd == Decimal("0.001")

    async def test_record_called_with_actual_usage(self):
        provider = _make_provider(input_tokens=15, output_tokens=7)
        guard = _make_guard()
        tool = AnswerLLMTool(provider=provider, guard=guard)
        conn = _make_conn()
        request = AnswerRequest(
            messages=_MESSAGES,
            provider_name="ollama",
            model_name="llama3.2",
            purpose="answer",
        )
        await tool.execute(request, conn)
        guard.record.assert_awaited_once()
        call_kwargs = guard.record.call_args.kwargs
        assert call_kwargs["input_tokens"] == 15
        assert call_kwargs["output_tokens"] == 7
        assert call_kwargs.get("status", "ok") == "ok"

    async def test_reserve_called_before_stream(self):
        provider = _make_provider()
        guard = _make_guard()
        tool = AnswerLLMTool(provider=provider, guard=guard)
        conn = _make_conn()
        await tool.execute(AnswerRequest(messages=_MESSAGES), conn)
        guard.reserve.assert_awaited_once()
        guard.record.assert_awaited_once()

    async def test_empty_delta_list_yields_empty_text(self):
        provider = _make_provider(texts=[])
        guard = _make_guard()
        tool = AnswerLLMTool(provider=provider, guard=guard)
        conn = _make_conn()
        result = await tool.execute(AnswerRequest(messages=_MESSAGES), conn)
        assert result.text == ""


# ---------------------------------------------------------------------------
# CapExceededError propagation
# ---------------------------------------------------------------------------


class TestCapExceededError:
    async def test_cap_exceeded_propagates(self):
        provider = _make_provider()
        guard = _make_guard()
        guard.reserve.side_effect = CapExceededError(
            "day_cap", Decimal("0.01"), Decimal("0.99"), Decimal("1.00")
        )
        tool = AnswerLLMTool(provider=provider, guard=guard)
        conn = _make_conn()
        with pytest.raises(CapExceededError):
            await tool.execute(AnswerRequest(messages=_MESSAGES), conn)

    async def test_record_not_called_on_cap_exceeded(self):
        provider = _make_provider()
        guard = _make_guard()
        guard.reserve.side_effect = CapExceededError(
            "day_cap", Decimal("0.01"), Decimal("0.99"), Decimal("1.00")
        )
        tool = AnswerLLMTool(provider=provider, guard=guard)
        conn = _make_conn()
        with pytest.raises(CapExceededError):
            await tool.execute(AnswerRequest(messages=_MESSAGES), conn)
        guard.record.assert_not_awaited()


# ---------------------------------------------------------------------------
# IntegrationError handling
# ---------------------------------------------------------------------------


class TestIntegrationError:
    async def test_integration_error_is_reraised(self):
        err = IntegrationError("ollama", "connection refused")
        provider = _make_provider(raise_on_stream=err)
        guard = _make_guard()
        tool = AnswerLLMTool(provider=provider, guard=guard)
        conn = _make_conn()
        with pytest.raises(IntegrationError):
            await tool.execute(AnswerRequest(messages=_MESSAGES), conn)

    async def test_record_called_with_failed_status_on_integration_error(self):
        err = IntegrationError("ollama", "timeout")
        provider = _make_provider(raise_on_stream=err)
        guard = _make_guard()
        tool = AnswerLLMTool(provider=provider, guard=guard)
        conn = _make_conn()
        with pytest.raises(IntegrationError):
            await tool.execute(AnswerRequest(messages=_MESSAGES), conn)
        guard.record.assert_awaited_once()
        call_kwargs = guard.record.call_args.kwargs
        assert call_kwargs["status"] == "failed"

    async def test_record_called_with_zero_cost_on_integration_error(self):
        err = IntegrationError("ollama", "timeout")
        provider = _make_provider(raise_on_stream=err)
        guard = _make_guard()
        tool = AnswerLLMTool(provider=provider, guard=guard)
        conn = _make_conn()
        with pytest.raises(IntegrationError):
            await tool.execute(AnswerRequest(messages=_MESSAGES), conn)
        call_kwargs = guard.record.call_args.kwargs
        assert call_kwargs["cost"] == Decimal("0")

    async def test_record_called_with_zero_tokens_on_integration_error(self):
        err = IntegrationError("ollama", "timeout")
        provider = _make_provider(raise_on_stream=err)
        guard = _make_guard()
        tool = AnswerLLMTool(provider=provider, guard=guard)
        conn = _make_conn()
        with pytest.raises(IntegrationError):
            await tool.execute(AnswerRequest(messages=_MESSAGES), conn)
        call_kwargs = guard.record.call_args.kwargs
        assert call_kwargs["input_tokens"] == 0
        assert call_kwargs["output_tokens"] == 0
