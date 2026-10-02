"""Gmail SMTP sender: STARTTLS on port 587 with an app password.

Retry policy: up to 3 attempts on transient ``SMTPException`` / ``OSError``
with exponential-jitter backoff from the core retry module.

Rate-limiting is the responsibility of the caller (``mailer.py``), which has
access to the database connection and the rate-limit table.
"""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.core.errors import IntegrationError
from src.core.retry import retry_policy
from src.integrations.email.base import EmailMessage

__all__ = ["RATE_LIMIT_KEY", "RATE_LIMIT_WINDOW_S", "GmailSMTPSender"]

# Exposed so callers (mailer.py) can reference the canonical key/window values.
RATE_LIMIT_KEY = "smtp.gmail"
RATE_LIMIT_WINDOW_S = 3600
_RATE_LIMIT_PER_HOUR = 450


class GmailSMTPSender:
    """Send via Gmail SMTP (STARTTLS, port 587) with an app password.

    Implements the :class:`~src.integrations.email.base.EmailSender` Protocol.

    Args:
        host: SMTP host (default ``smtp.gmail.com``).
        port: SMTP port (default ``587``).
        user: Gmail address used to authenticate.
        password: App password (not the account password).
        from_address: ``From:`` header value; defaults to *user*.
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        *,
        from_address: str | None = None,
    ) -> None:
        """Store connection details; no SMTP connection is opened yet."""
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._from = from_address or user

    async def send(self, message: EmailMessage) -> None:
        """Deliver *message* via Gmail SMTP.

        Rate-checking is done separately by the mailer (which has a DB
        connection); this method only handles the SMTP I/O.

        Raises:
            IntegrationError: if SMTP delivery fails after retries.
        """
        mime = self._build_mime(message)
        policy = retry_policy(
            max_attempts=3,
            retry_on=(smtplib.SMTPException, OSError),
        )
        try:
            for attempt in policy:
                with attempt:
                    self._send_smtp(mime, message.to)
        except (smtplib.SMTPException, OSError) as exc:
            raise IntegrationError("smtp", str(exc)) from exc

    def _build_mime(self, message: EmailMessage) -> MIMEMultipart | MIMEText:
        if message.body_html:
            msg: MIMEMultipart | MIMEText = MIMEMultipart("alternative")
            msg["Subject"] = message.subject
            msg["From"] = self._from
            msg["To"] = message.to
            msg.attach(MIMEText(message.body_text, "plain"))
            msg.attach(MIMEText(message.body_html, "html"))
        else:
            msg = MIMEText(message.body_text, "plain")
            msg["Subject"] = message.subject
            msg["From"] = self._from
            msg["To"] = message.to
        return msg

    def _send_smtp(self, mime: MIMEMultipart | MIMEText, to: str) -> None:
        with smtplib.SMTP(self._host, self._port) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(self._user, self._password)
            smtp.sendmail(self._from, to, mime.as_string())
