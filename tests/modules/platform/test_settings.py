"""Tests for 1Stop settings: parsing, normalisation and production boot checks."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from pydantic import ValidationError

from src.core.config import Environment
from src.core.errors import ConfigurationError
from src.modules.platform.settings import (
    LLMProvider,
    OneStopSettings,
    get_onestop_settings,
    reset_onestop_settings,
)

PRODUCTION_READY: dict[str, Any] = {
    "environment": Environment.PRODUCTION,
    "database_url": "postgresql://user:pw@db.example:5432/postgres",
    "session_secret": "x" * 40,
    "bootstrap_admin_email": "admin@example.com",
    "smtp_user": "sender@example.com",
    "smtp_password": "app-password",
    "smtp_from": "sender@example.com",
    "llm_provider": LLMProvider.ANTHROPIC,
    "llm_model": "claude-haiku-4-5-20251001",
    "anthropic_api_key": "key",
}


def make(**overrides: Any) -> OneStopSettings:
    """Build settings without reading any real .env file."""
    return OneStopSettings(_env_file=None, **overrides)


@pytest.fixture(autouse=True)
def _reset_cache() -> Iterator[None]:
    reset_onestop_settings()
    yield
    reset_onestop_settings()


class TestDefaults:
    def test_development_defaults_need_no_secrets(self):
        settings = make()
        assert settings.environment is Environment.DEVELOPMENT
        assert settings.llm_provider is LLMProvider.OLLAMA
        assert settings.spend_cap_day_usd == 1.0
        assert settings.spend_cap_month_usd == 10.0
        assert settings.allowed_emails == []

    def test_secrets_are_not_revealed_in_repr(self):
        settings = make(database_url="postgresql://u:topsecret@h/db", session_secret="s3cret")
        assert "topsecret" not in repr(settings)
        assert "s3cret" not in repr(settings)


class TestEmails:
    def test_comma_separated_list_is_split_normalised_and_deduplicated(self):
        settings = make(allowed_emails=" A@Example.com, b@example.com ,a@example.com,, ")
        assert settings.allowed_emails == ["a@example.com", "b@example.com"]

    def test_list_input_is_accepted(self):
        assert make(allowed_emails=["X@Y.io"]).allowed_emails == ["x@y.io"]

    def test_invalid_allowed_email_is_rejected(self):
        with pytest.raises(ValidationError, match="invalid address"):
            make(allowed_emails="good@example.com, not-an-email")

    def test_single_email_is_normalised_and_blank_becomes_none(self):
        settings = make(bootstrap_admin_email=" Admin@Example.COM ", smtp_from="  ")
        assert settings.bootstrap_admin_email == "admin@example.com"
        assert settings.smtp_from is None

    def test_invalid_single_email_is_rejected(self):
        with pytest.raises(ValidationError, match="Invalid email"):
            make(bootstrap_admin_email="admin")

    def test_env_var_comma_list_is_parsed(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_EMAILS", "one@example.com,two@example.com")
        assert make().allowed_emails == ["one@example.com", "two@example.com"]


class TestSpendCaps:
    def test_day_cap_above_month_cap_is_refused(self):
        with pytest.raises(ConfigurationError, match="SPEND_CAP_DAY_USD"):
            make(spend_cap_day_usd=20.0, spend_cap_month_usd=10.0)

    def test_negative_cap_is_refused(self):
        with pytest.raises(ValidationError):
            make(spend_cap_day_usd=-1.0)


class TestProductionBoot:
    def test_complete_production_configuration_boots(self):
        settings = make(**PRODUCTION_READY)
        assert settings.production_problems() == []

    def test_empty_production_configuration_lists_every_problem_at_once(self):
        with pytest.raises(ConfigurationError) as excinfo:
            make(environment=Environment.PRODUCTION)
        message = str(excinfo.value)
        for name in (
            "DATABASE_URL",
            "BOOTSTRAP_ADMIN_EMAIL",
            "SMTP_USER",
            "SMTP_PASSWORD",
            "SMTP_FROM",
            "SESSION_SECRET",
            "LLM_MODEL",
        ):
            assert name in message

    def test_short_session_secret_is_refused(self):
        with pytest.raises(ConfigurationError, match="SESSION_SECRET"):
            make(**{**PRODUCTION_READY, "session_secret": "short"})

    @pytest.mark.parametrize(
        ("provider", "key_field", "key_name"),
        [
            (LLMProvider.ANTHROPIC, "anthropic_api_key", "ANTHROPIC_API_KEY"),
            (LLMProvider.GEMINI, "gemini_api_key", "GEMINI_API_KEY"),
        ],
    )
    def test_paid_provider_requires_its_key(self, provider, key_field, key_name):
        config = {**PRODUCTION_READY, "llm_provider": provider}
        config.pop("anthropic_api_key")
        config.pop(key_field, None)
        with pytest.raises(ConfigurationError, match=key_name):
            make(**config)

    def test_ollama_needs_no_api_key(self):
        config = {**PRODUCTION_READY, "llm_provider": LLMProvider.OLLAMA}
        config.pop("anthropic_api_key")
        assert make(**config).production_problems() == []

    def test_core_guardrail_rule_still_applies(self):
        with pytest.raises(ConfigurationError, match="GUARDRAILS_ENABLED"):
            make(**{**PRODUCTION_READY, "guardrails_enabled": False})


class TestCache:
    def test_settings_are_parsed_once_and_resettable(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "first")
        first = get_onestop_settings()
        monkeypatch.setenv("LLM_MODEL", "second")
        assert get_onestop_settings() is first
        reset_onestop_settings()
        assert get_onestop_settings().llm_model == "second"
