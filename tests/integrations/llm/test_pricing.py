"""Tests for src.integrations.llm.pricing."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.core.errors import ConfigurationError
from src.integrations.llm.pricing import _PRICES, cost_usd


class TestCostUsd:
    def test_ollama_is_free(self):
        assert cost_usd("ollama", "llama3.2", 1_000, 500) == Decimal("0")

    def test_ollama_any_model_is_free(self):
        assert cost_usd("OLLAMA", "some-future-model", 999_999, 999_999) == Decimal("0")

    def test_ollama_zero_tokens_is_free(self):
        assert cost_usd("ollama", "llama3.2", 0, 0) == Decimal("0")

    def test_unknown_model_raises(self):
        with pytest.raises(ConfigurationError, match="no-such-model"):
            cost_usd("anthropic", "no-such-model", 100, 100)

    def test_error_names_the_model_and_provider(self):
        with pytest.raises(ConfigurationError, match="anthropic"):
            cost_usd("anthropic", "ghost-model", 100, 100)

    def test_haiku_input_cost(self):
        # 1M input tokens at $0.80/MTok = $0.80
        result = cost_usd("anthropic", "claude-haiku-4-5-20251001", 1_000_000, 0)
        assert result == Decimal("0.80")

    def test_haiku_output_cost(self):
        # 1M output tokens at $4.00/MTok = $4.00
        result = cost_usd("anthropic", "claude-haiku-4-5-20251001", 0, 1_000_000)
        assert result == Decimal("4.00")

    def test_combined_cost(self):
        # 500k input @ $0.80/MTok + 200k output @ $4.00/MTok
        # = 0.40 + 0.80 = $1.20
        result = cost_usd("anthropic", "claude-haiku-4-5-20251001", 500_000, 200_000)
        assert result == Decimal("0.40") + Decimal("0.80")

    def test_model_name_is_case_insensitive(self):
        lower = cost_usd("anthropic", "claude-haiku-4-5-20251001", 1000, 1000)
        upper = cost_usd("anthropic", "CLAUDE-HAIKU-4-5-20251001", 1000, 1000)
        assert lower == upper

    def test_zero_tokens_returns_zero(self):
        result = cost_usd("anthropic", "claude-sonnet-5-5", 0, 0)
        assert result == Decimal("0")

    def test_all_known_models_reachable(self):
        """Every entry in _PRICES must be reachable and return a positive cost."""
        for model in _PRICES:
            result = cost_usd("anthropic", model, 1_000_000, 1_000_000)
            assert result > Decimal("0"), f"model {model!r} returned non-positive cost"

    def test_gemini_flash_known(self):
        result = cost_usd("gemini", "gemini-2.0-flash", 1_000_000, 0)
        assert result == Decimal("0.10")
