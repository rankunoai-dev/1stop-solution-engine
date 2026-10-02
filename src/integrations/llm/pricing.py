"""LLM pricing table — cost per token for each supported model (ADR 0005).

Prices are USD per 1,000,000 tokens (per-MTok).  Ollama is always free.
Add new models to ``_PRICES`` as they are adopted; the function raises
``ConfigurationError`` for any unknown paid-provider model so a bad model name
is caught at call time rather than silently costing nothing.

Prices are estimates based on publicly available information and may lag
provider announcements.  Update the table alongside ``LLM_MODEL`` changes.
"""

from __future__ import annotations

from decimal import Decimal

from src.core.errors import ConfigurationError

__all__ = ["cost_usd"]

# (input_usd_per_mtok, output_usd_per_mtok)
_PRICES: dict[str, tuple[str, str]] = {
    # Anthropic — Claude 4/5 family (estimates; update when pricing is published)
    "claude-haiku-4-5-20251001": ("0.80", "4.00"),
    "claude-sonnet-5-5": ("3.00", "15.00"),
    "claude-opus-5-5": ("15.00", "75.00"),
    "claude-fable-5-1": ("1.00", "5.00"),
    # Legacy aliases kept so old llm_calls rows can be repriced
    "claude-3-haiku-20240307": ("0.25", "1.25"),
    "claude-3-5-haiku-20241022": ("0.80", "4.00"),
    "claude-3-5-sonnet-20241022": ("3.00", "15.00"),
    "claude-3-opus-20240229": ("15.00", "75.00"),
    # Google Gemini
    "gemini-1.5-flash": ("0.075", "0.30"),
    "gemini-1.5-flash-8b": ("0.0375", "0.15"),
    "gemini-2.0-flash": ("0.10", "0.40"),
    "gemini-2.0-flash-lite": ("0.075", "0.30"),
}

_MTOK = Decimal("1000000")


def cost_usd(provider: str, model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Return the cost in USD for one LLM call.

    Ollama is always free.  Unknown models for paid providers raise
    ``ConfigurationError`` rather than returning zero, to prevent silent
    budget under-reporting.

    Args:
        provider: Lower-case provider name, e.g. ``"ollama"`` or ``"anthropic"``.
        model: Exact model string as passed to the provider API.
        input_tokens: Number of prompt tokens consumed.
        output_tokens: Number of completion tokens generated.
    """
    if provider.lower() == "ollama":
        return Decimal("0")

    key = model.lower()
    if key not in _PRICES:
        msg = (
            f"No pricing entry for model '{model}' (provider '{provider}'). "
            "Add it to src/integrations/llm/pricing.py."
        )
        raise ConfigurationError(msg)

    in_rate, out_rate = _PRICES[key]
    return (
        Decimal(in_rate) * Decimal(input_tokens) / _MTOK
        + Decimal(out_rate) * Decimal(output_tokens) / _MTOK
    )
