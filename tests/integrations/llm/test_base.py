"""Tests for src.integrations.llm.base — Protocol and data models."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from decimal import Decimal

from src.integrations.llm.base import Delta, LLMProvider, Message, Usage

# ---------------------------------------------------------------------------
# Dataclass field tests
# ---------------------------------------------------------------------------


class TestMessage:
    def test_fields_present(self):
        msg = Message(role="user", content="hello")
        assert msg.role == "user"
        assert msg.content == "hello"

    def test_assistant_role(self):
        msg = Message(role="assistant", content="hi there")
        assert msg.role == "assistant"

    def test_system_role(self):
        msg = Message(role="system", content="You are helpful.")
        assert msg.role == "system"


class TestDelta:
    def test_text_field(self):
        d = Delta(text="chunk")
        assert d.text == "chunk"

    def test_empty_text(self):
        d = Delta(text="")
        assert d.text == ""


class TestUsage:
    def test_fields_present(self):
        u = Usage(input_tokens=10, output_tokens=5, cost_usd=Decimal("0.001"))
        assert u.input_tokens == 10
        assert u.output_tokens == 5
        assert u.cost_usd == Decimal("0.001")

    def test_zero_cost(self):
        u = Usage(input_tokens=100, output_tokens=50, cost_usd=Decimal("0"))
        assert u.cost_usd == Decimal("0")

    def test_cost_usd_is_decimal(self):
        u = Usage(input_tokens=1, output_tokens=1, cost_usd=Decimal("0.123456"))
        assert isinstance(u.cost_usd, Decimal)


# ---------------------------------------------------------------------------
# Protocol satisfaction tests
# ---------------------------------------------------------------------------


class _ConcreteProvider:
    """Minimal struct that satisfies LLMProvider for structural typing tests."""

    async def stream(
        self,
        messages: list[Message],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> AsyncGenerator[Delta, None]:
        yield Delta(text="hi")

    async def count_tokens(self, messages: list[Message]) -> int:
        return 10

    async def get_usage(self) -> Usage:
        return Usage(input_tokens=10, output_tokens=5, cost_usd=Decimal("0"))


class TestLLMProviderProtocol:
    def test_concrete_implementation_satisfies_protocol(self):
        provider = _ConcreteProvider()
        assert isinstance(provider, LLMProvider)

    def test_missing_stream_does_not_satisfy_protocol(self):
        class _NoStream:
            async def count_tokens(self, messages: list[Message]) -> int:
                return 0

            async def get_usage(self) -> Usage:
                return Usage(0, 0, Decimal("0"))

        assert not isinstance(_NoStream(), LLMProvider)

    def test_missing_count_tokens_does_not_satisfy_protocol(self):
        class _NoCount:
            async def stream(
                self, messages: list[Message], *, max_tokens: int = 1024, temperature: float = 0.7
            ) -> AsyncGenerator[Delta, None]:
                yield Delta(text="x")

            async def get_usage(self) -> Usage:
                return Usage(0, 0, Decimal("0"))

        assert not isinstance(_NoCount(), LLMProvider)

    def test_missing_get_usage_does_not_satisfy_protocol(self):
        class _NoUsage:
            async def stream(
                self, messages: list[Message], *, max_tokens: int = 1024, temperature: float = 0.7
            ) -> AsyncGenerator[Delta, None]:
                yield Delta(text="x")

            async def count_tokens(self, messages: list[Message]) -> int:
                return 0

        assert not isinstance(_NoUsage(), LLMProvider)

    def test_protocol_is_runtime_checkable(self):
        # A non-runtime-checkable Protocol raises TypeError on isinstance.
        # Calling isinstance here (without error) proves the decorator is active.
        class _Empty:
            pass

        # Should not raise TypeError; will return False because _Empty lacks methods.
        result = isinstance(_Empty(), LLMProvider)
        assert result is False
