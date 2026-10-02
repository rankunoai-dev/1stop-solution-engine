"""Unit tests for SSE event models and encode_sse."""

from __future__ import annotations

import json

from src.modules.assistant.events import (
    DoneEvent,
    ErrorEvent,
    StatusEvent,
    TokenEvent,
    encode_sse,
)


class TestStatusEvent:
    def test_default_fields(self):
        e = StatusEvent()
        assert e.type == "status"
        assert e.state == "thinking"
        assert e.conversation_id == ""

    def test_custom_state(self):
        e = StatusEvent(state="answering", conversation_id="abc")
        assert e.state == "answering"
        assert e.conversation_id == "abc"

    def test_type_literal(self):
        assert StatusEvent.type.__class__ is not None
        e = StatusEvent(state="done")
        assert e.type == "status"


class TestTokenEvent:
    def test_default_fields(self):
        e = TokenEvent()
        assert e.type == "token"
        assert e.text == ""
        assert e.conversation_id == ""

    def test_custom_text(self):
        e = TokenEvent(text="hello world", conversation_id="xyz")
        assert e.text == "hello world"
        assert e.conversation_id == "xyz"


class TestDoneEvent:
    def test_default_fields(self):
        e = DoneEvent()
        assert e.type == "done"
        assert e.conversation_id == ""
        assert e.input_tokens == 0
        assert e.output_tokens == 0
        assert e.cost_usd == 0.0

    def test_custom_values(self):
        e = DoneEvent(
            conversation_id="cid",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
        )
        assert e.input_tokens == 100
        assert e.output_tokens == 50
        assert e.cost_usd == 0.001

    def test_cost_usd_is_float(self):
        e = DoneEvent(cost_usd=1.5)
        assert isinstance(e.cost_usd, float)


class TestErrorEvent:
    def test_default_fields(self):
        e = ErrorEvent()
        assert e.type == "error"
        assert e.code == "internal_error"
        assert e.detail == ""
        assert e.conversation_id == ""

    def test_cap_reached_code(self):
        e = ErrorEvent(code="cap_reached", detail="over budget", conversation_id="cid")
        assert e.code == "cap_reached"
        assert e.detail == "over budget"

    def test_rate_limited_code(self):
        e = ErrorEvent(code="rate_limited")
        assert e.code == "rate_limited"


class TestEncodeSse:
    def test_format_starts_with_data(self):
        result = encode_sse(StatusEvent(state="thinking", conversation_id="c1"))
        assert result.startswith("data: ")

    def test_format_ends_with_double_newline(self):
        result = encode_sse(StatusEvent())
        assert result.endswith("\n\n")

    def test_status_event_json(self):
        e = StatusEvent(state="answering", conversation_id="cid")
        result = encode_sse(e)
        payload = json.loads(result[len("data: ") :].strip())
        assert payload["type"] == "status"
        assert payload["state"] == "answering"
        assert payload["conversation_id"] == "cid"

    def test_token_event_json(self):
        e = TokenEvent(text="hello", conversation_id="cid")
        result = encode_sse(e)
        payload = json.loads(result[len("data: ") :].strip())
        assert payload["type"] == "token"
        assert payload["text"] == "hello"

    def test_done_event_json(self):
        e = DoneEvent(conversation_id="cid", input_tokens=10, output_tokens=5, cost_usd=0.01)
        result = encode_sse(e)
        payload = json.loads(result[len("data: ") :].strip())
        assert payload["type"] == "done"
        assert payload["input_tokens"] == 10
        assert payload["output_tokens"] == 5
        assert payload["cost_usd"] == 0.01

    def test_error_event_json(self):
        e = ErrorEvent(code="cap_reached", detail="over budget", conversation_id="cid")
        result = encode_sse(e)
        payload = json.loads(result[len("data: ") :].strip())
        assert payload["type"] == "error"
        assert payload["code"] == "cap_reached"
        assert payload["detail"] == "over budget"

    def test_all_event_types_produce_valid_json(self):
        events = [
            StatusEvent(state="thinking"),
            TokenEvent(text="tok"),
            DoneEvent(),
            ErrorEvent(),
        ]
        for event in events:
            result = encode_sse(event)
            raw = result[len("data: ") :].strip()
            parsed = json.loads(raw)
            assert "type" in parsed
