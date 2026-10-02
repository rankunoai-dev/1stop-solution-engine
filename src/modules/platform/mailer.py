"""Idempotent email delivery backed by ``email_deliveries`` (ARCHITECTURE S4).

Flow
----
1. Insert a ``pending`` row keyed on *idempotency_key* (UNIQUE constraint).
   If a row already exists, return without sending — idempotency guarantee.
2. Check the Gmail hourly rate limit; raise ``RateLimitExceededError`` if over.
3. Call ``sender.send(message)``.
4. Update the row to ``sent`` (success) or ``failed`` (error, stores the
   message so ops can inspect it).

Templates
---------
Two built-in templates produce (subject, body_text, body_html) triples:

* ``login_code``:  magic-link / OTP email
* ``spend_alert``: LLM spend threshold notification

Custom templates can be passed as pre-built :class:`EmailMessage` objects
directly to :func:`send`.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from src.core.errors import RateLimitExceededError
from src.integrations.email.base import EmailMessage, EmailSender
from src.integrations.email.smtp_gmail import RATE_LIMIT_KEY, RATE_LIMIT_WINDOW_S
from src.modules.platform.rate_limit import check_and_increment
from src.modules.platform.tables import t_email_deliveries

_SMTP_RATE_LIMIT = 450

if TYPE_CHECKING:
    pass

__all__ = ["DeliveryError", "render_login_code", "render_spend_alert", "send"]

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DeliveryError(Exception):
    """Raised when the SMTP send fails and the failure has been persisted."""

    def __init__(self, delivery_id: uuid.UUID, detail: str) -> None:
        """Record which delivery row failed and the error text."""
        self.delivery_id = delivery_id
        self.detail = detail
        super().__init__(f"Email delivery {delivery_id} failed: {detail}")


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def render_login_code(to: str, code: str, expires_minutes: int = 10) -> EmailMessage:
    """Render the one-time login code email."""
    subject = "Your 1Stop login code"
    body_text = (
        f"Your 1Stop login code is: {code}\n\n"
        f"It expires in {expires_minutes} minutes.\n\n"
        "If you didn't request this, you can ignore this email."
    )
    body_html = (
        "<p>Your <strong>1Stop</strong> login code is:</p>"
        f"<p style='font-size:2em;letter-spacing:0.1em'><strong>{code}</strong></p>"
        f"<p>It expires in {expires_minutes} minutes.</p>"
        "<p>If you didn't request this, you can ignore this email.</p>"
    )
    return EmailMessage(to=to, subject=subject, body_text=body_text, body_html=body_html)


def render_spend_alert(to: str, spent_usd: float, ceiling_usd: float, period: str) -> EmailMessage:
    """Render the LLM spend threshold alert email."""
    pct = (spent_usd / ceiling_usd * 100) if ceiling_usd else 0
    subject = f"1Stop spend alert: {pct:.0f}% of {period} cap used"
    body_text = (
        f"LLM spend is at ${spent_usd:.4f} of the ${ceiling_usd:.2f} {period} cap "
        f"({pct:.0f}%).\n\nLog in to the admin panel to review or adjust the cap."
    )
    body_html = (
        "<p><strong>1Stop spend alert</strong></p>"
        f"<p>LLM spend is at <strong>${spent_usd:.4f}</strong> of the "
        f"<strong>${ceiling_usd:.2f}</strong> {period} cap "
        f"(<strong>{pct:.0f}%</strong>).</p>"
        "<p>Log in to the admin panel to review or adjust the cap.</p>"
    )
    return EmailMessage(to=to, subject=subject, body_text=body_text, body_html=body_html)


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------


async def send(
    conn: AsyncConnection,
    message: EmailMessage,
    *,
    sender: EmailSender,
    idempotency_key: str,
    template: str = "custom",
) -> uuid.UUID:
    """Deliver *message* exactly once, tracked in ``email_deliveries``.

    Args:
        conn: Open ``AsyncConnection``.  The delivery record is written within
            the caller's transaction.
        message: The email to send.
        sender: An :class:`EmailSender` implementation (injected; use
            :class:`~src.integrations.email.smtp_gmail.GmailSMTPSender` in
            production, a fake in tests).
        idempotency_key: Unique key that prevents duplicate sends.  If a row
            with this key already exists in ``email_deliveries``, the function
            returns that row's ``id`` immediately without sending.
        template: Label stored in the ``template`` column for observability.
            Use ``"login_code"`` or ``"spend_alert"`` for the built-in ones.

    Returns:
        The ``id`` of the ``email_deliveries`` row (existing or newly created).

    Raises:
        RateLimitExceededError: if the Gmail hourly rate limit is exceeded
            (delivery row is NOT created).
        DeliveryError: if the SMTP send fails (delivery row persisted as
            ``failed``).
    """
    # 1. Idempotency: insert pending row; on conflict return existing id.
    row_id = uuid.uuid4()
    stmt = (
        pg_insert(t_email_deliveries)
        .values(
            id=row_id,
            idempotency_key=idempotency_key,
            to_email=message.to,
            template=template,
            status="pending",
        )
        .on_conflict_do_update(
            index_elements=["idempotency_key"],
            set_={"idempotency_key": t_email_deliveries.c.idempotency_key},
        )
        .returning(t_email_deliveries.c.id, t_email_deliveries.c.status)
    )
    result = await conn.execute(stmt)
    row = result.mappings().one()
    existing_id: uuid.UUID = uuid.UUID(str(row["id"]))

    # Already sent: skip.
    if row["status"] == "sent":
        return existing_id

    # 2. Rate limit check.
    allowed = await check_and_increment(conn, RATE_LIMIT_KEY, _SMTP_RATE_LIMIT, RATE_LIMIT_WINDOW_S)
    if not allowed:
        raise RateLimitExceededError(key="smtp.gmail", retry_after_s=3600.0)

    # 3. Attempt delivery.
    try:
        await sender.send(message)
    except Exception as exc:
        error_text = str(exc)
        await conn.execute(
            sa.update(t_email_deliveries)
            .where(t_email_deliveries.c.id == existing_id)
            .values(status="failed", error=error_text)
        )
        raise DeliveryError(existing_id, error_text) from exc

    # 4. Mark sent.
    await conn.execute(
        sa.update(t_email_deliveries)
        .where(t_email_deliveries.c.id == existing_id)
        .values(status="sent", sent_at=sa.text("now()"))
    )
    return existing_id


def _kwargs_for_send(**kwargs: Any) -> dict[str, Any]:
    """Utility kept for internal tests: build a minimal send() kwargs dict."""
    return kwargs
