"""1Stop configuration (ARCHITECTURE section 13).

Extends the core `Settings`, so the core rules still apply: values come only
from the environment or `.env`, secrets are `SecretStr`, and production refuses
to boot with guardrails disabled. This module adds the 1Stop values and one more
rule: production refuses to boot when a value it cannot run without is missing.
"""

from __future__ import annotations

import re
from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import NoDecode

from src.core.config import Environment, Settings
from src.core.errors import ConfigurationError

__all__ = ["LLMProvider", "OneStopSettings", "get_onestop_settings", "reset_onestop_settings"]

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MIN_SESSION_SECRET_LENGTH = 32


class LLMProvider(StrEnum):
    """Which LLM adapter is active (ADR 0008)."""

    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


class OneStopSettings(Settings):
    """All 1Stop runtime configuration. Field names map to upper-case env vars."""

    # -- Database ----------------------------------------------------------
    database_url: SecretStr | None = None

    # -- Sessions and access -----------------------------------------------
    session_secret: SecretStr | None = None
    bootstrap_admin_email: str | None = None
    allowed_emails: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # -- Email -------------------------------------------------------------
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = Field(default=587, gt=0, lt=65536)
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str | None = None

    # -- Sources -----------------------------------------------------------
    github_token: SecretStr | None = None
    gdrive_service_account_json_b64: SecretStr | None = None
    gdrive_registry_folder_id: str | None = None
    gdrive_registry_file_name: str | None = None

    # -- LLM and embeddings ------------------------------------------------
    llm_provider: LLMProvider = LLMProvider.OLLAMA
    llm_model: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # -- Spend caps in USD (ADR 0005) --------------------------------------
    spend_cap_day_usd: float = Field(default=1.0, ge=0.0)
    spend_cap_month_usd: float = Field(default=10.0, ge=0.0)

    # -- Application URL (used for CORS in production) ---------------------
    app_url: str | None = None

    # -- Observability -----------------------------------------------------
    sentry_dsn: SecretStr | None = None

    @field_validator("allowed_emails", mode="before")
    @classmethod
    def _split_emails(cls, value: Any) -> Any:
        """Accept a comma-separated string as well as a list."""
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("allowed_emails")
    @classmethod
    def _normalise_emails(cls, value: list[str]) -> list[str]:
        """Lower-case and validate every allowed email; drop duplicates."""
        result: list[str] = []
        for email in value:
            normalised = email.strip().lower()
            if not _EMAIL.match(normalised):
                msg = f"ALLOWED_EMAILS contains an invalid address: '{email}'"
                raise ValueError(msg)
            if normalised not in result:
                result.append(normalised)
        return result

    @field_validator("bootstrap_admin_email", "smtp_from")
    @classmethod
    def _normalise_single_email(cls, value: str | None) -> str | None:
        """Lower-case and validate an optional single email."""
        if value is None or not value.strip():
            return None
        normalised = value.strip().lower()
        if not _EMAIL.match(normalised):
            msg = f"Invalid email address: '{value}'"
            raise ValueError(msg)
        return normalised

    def model_post_init(self, context: Any, /) -> None:
        """Run the core boot checks, then the 1Stop ones."""
        super().model_post_init(context)
        if self.spend_cap_day_usd > self.spend_cap_month_usd:
            msg = "SPEND_CAP_DAY_USD cannot be larger than SPEND_CAP_MONTH_USD."
            raise ConfigurationError(msg)
        if self.environment is Environment.PRODUCTION:
            problems = self.production_problems()
            if problems:
                msg = "Production configuration is incomplete: " + "; ".join(problems)
                raise ConfigurationError(msg)

    def production_problems(self) -> list[str]:
        """List every value production cannot run without (empty when ready).

        All problems are reported together, so a deploy fails once with the
        full list instead of once per missing value.
        """
        problems: list[str] = []
        required = {
            "DATABASE_URL": self.database_url,
            "BOOTSTRAP_ADMIN_EMAIL": self.bootstrap_admin_email,
            "SMTP_USER": self.smtp_user,
            "SMTP_PASSWORD": self.smtp_password,
            "SMTP_FROM": self.smtp_from,
        }
        problems.extend(f"{name} is not set" for name, value in required.items() if not value)

        secret = self.session_secret.get_secret_value() if self.session_secret else ""
        if len(secret) < _MIN_SESSION_SECRET_LENGTH:
            problems.append(f"SESSION_SECRET must be at least {_MIN_SESSION_SECRET_LENGTH} chars")

        provider_keys = {
            LLMProvider.ANTHROPIC: ("ANTHROPIC_API_KEY", self.anthropic_api_key),
            LLMProvider.GEMINI: ("GEMINI_API_KEY", self.gemini_api_key),
        }
        if self.llm_provider in provider_keys:
            name, key = provider_keys[self.llm_provider]
            if key is None:
                problems.append(f"{name} is not set for LLM_PROVIDER={self.llm_provider}")
        if not self.llm_model:
            problems.append("LLM_MODEL is not set")
        return problems


@lru_cache(maxsize=1)
def get_onestop_settings() -> OneStopSettings:
    """Return the process-wide 1Stop settings, parsed once."""
    return OneStopSettings()


def reset_onestop_settings() -> None:
    """Clear the cached settings. Intended for tests only."""
    get_onestop_settings.cache_clear()
