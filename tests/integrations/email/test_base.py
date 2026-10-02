"""Tests for src.integrations.email.base."""

from __future__ import annotations

import pytest

from src.integrations.email.base import EmailMessage


class TestEmailMessage:
    def test_valid_message(self):
        msg = EmailMessage(
            to="user@example.com",
            subject="Hello",
            body_text="Hello, world!",
        )
        assert msg.to == "user@example.com"
        assert msg.subject == "Hello"
        assert msg.body_text == "Hello, world!"
        assert msg.body_html is None

    def test_valid_message_with_html(self):
        msg = EmailMessage(
            to="user@example.com",
            subject="Hello",
            body_text="Hello",
            body_html="<p>Hello</p>",
        )
        assert msg.body_html == "<p>Hello</p>"

    def test_invalid_email_rejected(self):
        from pydantic import ValidationError  # noqa: PLC0415

        with pytest.raises(ValidationError):
            EmailMessage(to="not-an-email", subject="X", body_text="X")

    def test_unknown_field_rejected(self):
        from pydantic import ValidationError  # noqa: PLC0415

        with pytest.raises(ValidationError):
            EmailMessage(
                to="user@example.com",
                subject="X",
                body_text="X",
                unknown_field="oops",
            )

    def test_empty_subject_allowed(self):
        msg = EmailMessage(to="user@example.com", subject="", body_text="Body")
        assert msg.subject == ""

    def test_domain_normalised_to_lowercase(self):
        # pydantic EmailStr lowercases the domain but preserves the local part.
        msg = EmailMessage(to="User@Example.COM", subject="X", body_text="X")
        assert msg.to.endswith("@example.com")
