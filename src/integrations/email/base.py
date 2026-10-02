"""Email integration contracts: EmailMessage model and EmailSender Protocol."""

from __future__ import annotations

from typing import Protocol

from pydantic import EmailStr

from src.core.schemas import StrictModel

__all__ = ["EmailMessage", "EmailSender"]


class EmailMessage(StrictModel):
    """A single outbound email."""

    to: EmailStr
    subject: str
    body_text: str
    body_html: str | None = None


class EmailSender(Protocol):
    """Anything that can deliver an :class:`EmailMessage`."""

    async def send(self, message: EmailMessage) -> None:
        """Deliver *message*.

        Raises:
            IntegrationError: if delivery fails after any retries.
        """
        ...
