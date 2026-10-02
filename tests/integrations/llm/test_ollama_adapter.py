"""Tests for src.integrations.llm.ollama_adapter — OllamaAdapter."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx

from src.core.errors import IntegrationError
from src.integrations.llm.base import Delta, Message, Usage
from src.integrations.llm.ollama_adapter import OllamaAdapter

_BASE = "http://localhost:11434"
_CHAT_URL = f"{_BASE}/api/chat"
_TAGS_URL = f"{_BASE}/api/tags"

_MSG = [Message(role="user", content="hello world")]

# Tags response that includes the test model so validate_model() passes.
_TAGS_RESP = httpx.Response(200, json={"models": [{"name": "llama3.2"}]})


def _ndjson(*chunks: str, done_counts: tuple[int, int] = (10, 5)) -> bytes:
    """Build NDJSON bytes from content chunks followed by a done line."""
    lines = [f'{{"message":{{"content":"{c}"}},"done":false}}' for c in chunks]
    in_tok, out_tok = done_counts
    lines.append(f'{{"done":true,"eval_count":{out_tok},"prompt_eval_count":{in_tok}}}')
    return ("\n".join(lines) + "\n").encode()


# ---------------------------------------------------------------------------
# stream() — happy path
# ---------------------------------------------------------------------------


class TestStream:
    async def test_yields_delta_per_content_chunk(self):
        content = _ndjson("Hello", " world", done_counts=(10, 5))
        with respx.mock:
            respx.get(_TAGS_URL).mock(return_value=_TAGS_RESP)
            respx.post(_CHAT_URL).mock(return_value=httpx.Response(200, content=content))
            adapter = OllamaAdapter(model="llama3.2", base_url=_BASE)
            deltas = [d async for d in adapter.stream(_MSG)]
        assert deltas == [Delta(text="Hello"), Delta(text=" world")]

    async def test_yields_nothing_for_empty_content(self):
        content = _ndjson(done_counts=(3, 0))
        with respx.mock:
            respx.get(_TAGS_URL).mock(return_value=_TAGS_RESP)
            respx.post(_CHAT_URL).mock(return_value=httpx.Response(200, content=content))
            adapter = OllamaAdapter(model="llama3.2", base_url=_BASE)
            deltas = [d async for d in adapter.stream(_MSG)]
        assert deltas == []

    async def test_empty_lines_in_response_are_skipped(self):
        # Insert blank lines; they must be ignored.
        raw = b"\n" + _ndjson("hi") + b"\n"
        with respx.mock:
            respx.get(_TAGS_URL).mock(return_value=_TAGS_RESP)
            respx.post(_CHAT_URL).mock(return_value=httpx.Response(200, content=raw))
            adapter = OllamaAdapter(model="llama3.2", base_url=_BASE)
            deltas = [d async for d in adapter.stream(_MSG)]
        assert deltas == [Delta(text="hi")]

    async def test_custom_base_url_used(self):
        custom = "http://gpu-server:11434"
        content = _ndjson("ok")
        with respx.mock:
            respx.get(f"{custom}/api/tags").mock(
                return_value=httpx.Response(200, json={"models": [{"name": "llama3.2"}]})
            )
            route = respx.post(f"{custom}/api/chat").mock(
                return_value=httpx.Response(200, content=content)
            )
            adapter = OllamaAdapter(model="llama3.2", base_url=custom)
            _ = [d async for d in adapter.stream(_MSG)]
        assert route.called


# ---------------------------------------------------------------------------
# stream() — token count capture
# ---------------------------------------------------------------------------


class TestStreamTokenCapture:
    async def test_stores_token_counts_from_done_line(self):
        content = _ndjson("hi", done_counts=(17, 8))
        with respx.mock:
            respx.get(_TAGS_URL).mock(return_value=_TAGS_RESP)
            respx.post(_CHAT_URL).mock(return_value=httpx.Response(200, content=content))
            adapter = OllamaAdapter(model="llama3.2", base_url=_BASE)
            _ = [d async for d in adapter.stream(_MSG)]
        assert adapter._input_tokens == 17
        assert adapter._output_tokens == 8


# ---------------------------------------------------------------------------
# get_usage()
# ---------------------------------------------------------------------------


class TestGetUsage:
    async def test_returns_usage_after_stream(self):
        content = _ndjson("answer", done_counts=(20, 10))
        with respx.mock:
            respx.get(_TAGS_URL).mock(return_value=_TAGS_RESP)
            respx.post(_CHAT_URL).mock(return_value=httpx.Response(200, content=content))
            adapter = OllamaAdapter(model="llama3.2", base_url=_BASE)
            _ = [d async for d in adapter.stream(_MSG)]
        usage = await adapter.get_usage()
        assert isinstance(usage, Usage)
        assert usage.input_tokens == 20
        assert usage.output_tokens == 10

    async def test_ollama_cost_is_zero(self):
        content = _ndjson("hi", done_counts=(5, 3))
        with respx.mock:
            respx.get(_TAGS_URL).mock(return_value=_TAGS_RESP)
            respx.post(_CHAT_URL).mock(return_value=httpx.Response(200, content=content))
            adapter = OllamaAdapter(model="llama3.2", base_url=_BASE)
            _ = [d async for d in adapter.stream(_MSG)]
        usage = await adapter.get_usage()
        assert usage.cost_usd == Decimal("0")

    async def test_zero_counts_before_any_stream(self):
        adapter = OllamaAdapter(model="llama3.2", base_url=_BASE)
        usage = await adapter.get_usage()
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0


# ---------------------------------------------------------------------------
# count_tokens()
# ---------------------------------------------------------------------------


class TestCountTokens:
    async def test_returns_positive_int_for_non_empty(self):
        adapter = OllamaAdapter(model="llama3.2", base_url=_BASE)
        count = await adapter.count_tokens([Message(role="user", content="hello world test")])
        assert count > 0
        assert isinstance(count, int)

    async def test_returns_zero_for_empty_messages(self):
        adapter = OllamaAdapter(model="llama3.2", base_url=_BASE)
        count = await adapter.count_tokens([])
        assert count == 0

    async def test_longer_content_yields_more_tokens(self):
        adapter = OllamaAdapter(model="llama3.2", base_url=_BASE)
        short = await adapter.count_tokens([Message(role="user", content="hi")])
        long_ = await adapter.count_tokens(
            [Message(role="user", content="this is a much longer message with many words")]
        )
        assert long_ > short

    async def test_multiple_messages_summed(self):
        adapter = OllamaAdapter(model="llama3.2", base_url=_BASE)
        one = await adapter.count_tokens([Message(role="user", content="hello world")])
        two = await adapter.count_tokens(
            [
                Message(role="user", content="hello world"),
                Message(role="assistant", content="hello world"),
            ]
        )
        assert two >= one  # at least as many tokens with more messages


# ---------------------------------------------------------------------------
# validate_model() — direct tests
# ---------------------------------------------------------------------------


class TestValidateModel:
    async def test_passes_when_model_in_tags(self):
        """No exception raised when the model is listed."""
        with respx.mock:
            respx.get(_TAGS_URL).mock(return_value=_TAGS_RESP)
            adapter = OllamaAdapter(model="llama3.2", base_url=_BASE)
            await adapter.validate_model()  # should not raise

    async def test_raises_when_model_not_in_tags(self):
        """IntegrationError raised when model is absent."""
        with respx.mock:
            respx.get(_TAGS_URL).mock(
                return_value=httpx.Response(200, json={"models": [{"name": "other-model"}]})
            )
            adapter = OllamaAdapter(model="llama3.2", base_url=_BASE)
            with pytest.raises(IntegrationError) as exc_info:
                await adapter.validate_model()
        assert "llama3.2" in exc_info.value.detail

    async def test_raises_on_tags_http_error(self):
        """IntegrationError raised when /api/tags returns an error."""
        with respx.mock:
            respx.get(_TAGS_URL).mock(return_value=httpx.Response(503, content=b"unavailable"))
            adapter = OllamaAdapter(model="llama3.2", base_url=_BASE)
            with pytest.raises(IntegrationError):
                await adapter.validate_model()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    async def test_http_500_raises_integration_error(self):
        with respx.mock:
            respx.get(_TAGS_URL).mock(return_value=_TAGS_RESP)
            respx.post(_CHAT_URL).mock(
                return_value=httpx.Response(500, content=b"Internal Server Error")
            )
            adapter = OllamaAdapter(model="llama3.2", base_url=_BASE)
            with pytest.raises(IntegrationError) as exc_info:
                async for _ in adapter.stream(_MSG):
                    pass
        assert exc_info.value.service == "ollama"

    async def test_http_404_raises_integration_error(self):
        with respx.mock:
            respx.get(_TAGS_URL).mock(return_value=_TAGS_RESP)
            respx.post(_CHAT_URL).mock(return_value=httpx.Response(404, content=b"Not Found"))
            adapter = OllamaAdapter(model="llama3.2", base_url=_BASE)
            with pytest.raises(IntegrationError):
                async for _ in adapter.stream(_MSG):
                    pass

    async def test_malformed_json_line_raises_integration_error(self):
        bad_content = b"this-is-not-json\n"
        with respx.mock:
            respx.get(_TAGS_URL).mock(return_value=_TAGS_RESP)
            respx.post(_CHAT_URL).mock(return_value=httpx.Response(200, content=bad_content))
            adapter = OllamaAdapter(model="llama3.2", base_url=_BASE)
            with pytest.raises(IntegrationError) as exc_info:
                async for _ in adapter.stream(_MSG):
                    pass
        assert "JSON decode error" in exc_info.value.detail

    async def test_integration_error_service_is_ollama(self):
        with respx.mock:
            respx.get(_TAGS_URL).mock(return_value=_TAGS_RESP)
            respx.post(_CHAT_URL).mock(return_value=httpx.Response(500, content=b"err"))
            adapter = OllamaAdapter(model="llama3.2", base_url=_BASE)
            with pytest.raises(IntegrationError) as exc_info:
                async for _ in adapter.stream(_MSG):
                    pass
        assert exc_info.value.service == "ollama"
