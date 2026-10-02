"""Tests for src.integrations.email.smtp_gmail."""

from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

import pytest

from src.core.errors import IntegrationError
from src.integrations.email.base import EmailMessage
from src.integrations.email.smtp_gmail import (
    RATE_LIMIT_KEY,
    RATE_LIMIT_WINDOW_S,
    GmailSMTPSender,
)


def _sender() -> GmailSMTPSender:
    return GmailSMTPSender(
        host="smtp.gmail.com",
        port=587,
        user="test@example.com",
        password="app-password",
        from_address="noreply@example.com",
    )


def _msg() -> EmailMessage:
    return EmailMessage(
        to="recipient@example.com",
        subject="Test",
        body_text="Hello",
    )


class TestGmailSMTPSender:
    async def test_send_calls_smtp(self):
        sender = _sender()
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_ctx = MagicMock()
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
            await sender.send(_msg())
        mock_ctx.starttls.assert_called_once()
        mock_ctx.login.assert_called_once_with("test@example.com", "app-password")
        mock_ctx.sendmail.assert_called_once()

    async def test_send_raises_integration_error_on_smtp_failure(self):
        sender = _sender()
        with (
            patch.object(sender, "_send_smtp", side_effect=smtplib.SMTPException("boom")),
            pytest.raises(IntegrationError) as exc_info,
        ):
            await sender.send(_msg())
        assert exc_info.value.service == "smtp"
        assert "boom" in exc_info.value.detail

    async def test_send_retries_on_transient_error(self):
        sender = _sender()
        call_count = 0

        def _flaky(*_args):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise smtplib.SMTPException("transient")

        with patch.object(sender, "_send_smtp", side_effect=_flaky):
            await sender.send(_msg())
        assert call_count == 3

    async def test_send_raises_after_max_retries(self):
        sender = _sender()
        with (
            patch.object(sender, "_send_smtp", side_effect=smtplib.SMTPException("always")),
            pytest.raises(IntegrationError),
        ):
            await sender.send(_msg())

    def test_build_mime_plain(self):
        sender = _sender()
        msg = EmailMessage(to="x@y.com", subject="S", body_text="Body")
        mime = sender._build_mime(msg)
        assert mime["Subject"] == "S"
        assert mime["From"] == "noreply@example.com"
        assert mime["To"] == "x@y.com"

    def test_build_mime_multipart(self):
        from email.mime.multipart import MIMEMultipart  # noqa: PLC0415

        sender = _sender()
        msg = EmailMessage(to="x@y.com", subject="S", body_text="Body", body_html="<p>Body</p>")
        mime = sender._build_mime(msg)
        assert isinstance(mime, MIMEMultipart)

    def test_rate_limit_constants(self):
        assert RATE_LIMIT_KEY == "smtp.gmail"
        assert RATE_LIMIT_WINDOW_S == 3600

    def test_from_address_defaults_to_user(self):
        sender = GmailSMTPSender(
            host="smtp.gmail.com",
            port=587,
            user="sender@example.com",
            password="pw",
        )
        assert sender._from == "sender@example.com"
