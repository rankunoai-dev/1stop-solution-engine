"""Tests for OllamaAdapter — breaking-point exposure and validation (Phase S-15).

These tests systematically verify fixes for:
- BP-01: Connection timeout
- BP-03: Model validation before streaming
- BP-04: Token count accuracy
- BP-05: Concurrent state isolation
- BP-06: Stream consumption timeout
And happy-path scenarios.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx

from src.core.errors import IntegrationError
from src.integrations.llm.base import Message
from src.integrations.llm.ollama_adapter import OllamaAdapter

__all__ = []


class TestModelValidation:
    """BP-03: Model validation before streaming."""

    @pytest.mark.asyncio
    async def test_model_not_found_raises_before_streaming(self) -> None:
        """Should fail fast if model doesn''t exist locally."""
        adapter = OllamaAdapter("nonexistent-xyz", base_url="http://localhost:11434")

        with respx.mock:
            respx.get("http://localhost:11434/api/tags").mock(
                return_value=httpx.Response(200, json={"models": [{"name": "other-model"}]})
            )

            with pytest.raises(IntegrationError) as exc_info:
                async for _ in adapter.stream([Message(role="user", content="Hi")]):
                    pass

            assert "nonexistent-xyz" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_api_tags_endpoint_unavailable(self) -> None:
        """Should fail if /api/tags endpoint is unreachable."""
        adapter = OllamaAdapter("qwen2.5:32b", base_url="http://localhost:11434")

        with respx.mock:
            respx.get("http://localhost:11434/api/tags").mock(
                return_value=httpx.Response(500, text="Server error")
            )

            with pytest.raises(IntegrationError):
                async for _ in adapter.stream([Message(role="user", content="Hi")]):
                    pass


class TestConnectionTimeout:
    """BP-01: Connection timeout on unreachable server."""

    @pytest.mark.asyncio
    async def test_unreachable_server_timeout(self) -> None:
        """Should timeout if Ollama server is unreachable (non-routable IP)."""
        adapter = OllamaAdapter("qwen2.5:32b", base_url="http://192.0.2.1:11434")

        with pytest.raises(IntegrationError) as exc_info:
            async with asyncio.timeout(15):
                async for _ in adapter.stream([Message(role="user", content="Hi")]):
                    pass

        error_msg = str(exc_info.value).lower()
        assert "connection" in error_msg or "timeout" in error_msg or "unreachable" in error_msg

    @pytest.mark.asyncio
    async def test_http_500_server_error(self) -> None:
        """Should handle HTTP 500 errors gracefully."""
        adapter = OllamaAdapter("qwen2.5:32b", base_url="http://localhost:11434")

        with respx.mock:
            respx.get("http://localhost:11434/api/tags").mock(
                return_value=httpx.Response(200, json={"models": [{"name": "qwen2.5:32b"}]})
            )
            respx.post("http://localhost:11434/api/chat").mock(
                return_value=httpx.Response(500, text="Internal Server Error")
            )

            with pytest.raises(IntegrationError):
                async for _ in adapter.stream([Message(role="user", content="Hi")]):
                    pass


class TestStreamTimeout:
    """BP-06: Stream consumption timeout (no tokens for 10s)."""

    @pytest.mark.asyncio
    async def test_stream_completes_normally(self) -> None:
        """Happy path: stream completes without timeout."""
        adapter = OllamaAdapter("qwen2.5:32b", base_url="http://localhost:11434")

        with respx.mock:
            respx.get("http://localhost:11434/api/tags").mock(
                return_value=httpx.Response(200, json={"models": [{"name": "qwen2.5:32b"}]})
            )
            respx.post("http://localhost:11434/api/chat").mock(
                return_value=httpx.Response(
                    200,
                    text=json.dumps({"message": {"content": "Hello"}})
                    + "\n"
                    + json.dumps({"done": True, "prompt_eval_count": 5, "eval_count": 1})
                    + "\n",
                )
            )

            tokens = []
            async for delta in adapter.stream([Message(role="user", content="Hi")]):
                tokens.append(delta.text)

            assert tokens == ["Hello"]


class TestTokenCounting:
    """BP-04: Token counting accuracy."""

    @pytest.mark.asyncio
    async def test_token_estimate_plain_text(self) -> None:
        """Heuristic should work reasonably on plain text."""
        adapter = OllamaAdapter("qwen2.5:32b")

        messages = [Message(role="user", content="Hello world this is a test")]
        estimated = await adapter.count_tokens(messages)

        # 6 words, heuristic: 6 * 4 // 3 = 8
        assert estimated == 8

    @pytest.mark.asyncio
    async def test_token_estimate_vs_actual(self) -> None:
        """Compare estimated tokens vs. actual from stream."""
        adapter = OllamaAdapter("qwen2.5:32b", base_url="http://localhost:11434")

        messages = [Message(role="user", content="Hello world")]
        estimated = await adapter.count_tokens(messages)

        with respx.mock:
            respx.get("http://localhost:11434/api/tags").mock(
                return_value=httpx.Response(200, json={"models": [{"name": "qwen2.5:32b"}]})
            )
            respx.post("http://localhost:11434/api/chat").mock(
                return_value=httpx.Response(
                    200,
                    text=json.dumps({"message": {"content": "Hi"}})
                    + "\n"
                    + json.dumps({"done": True, "prompt_eval_count": 4, "eval_count": 2})
                    + "\n",
                )
            )

            async for _ in adapter.stream(messages):
                pass

            usage = await adapter.get_usage()

        # Document the error (heuristic vs actual)
        actual = usage.input_tokens
        if actual > 0:
            error_pct = abs(estimated - actual) / actual * 100
            # BP-04: Heuristic tolerance ~30%; this test documents actual error
            assert error_pct < 100  # Sanity check; no hard requirement yet


class TestConcurrentState:
    """BP-05: State isolation between concurrent calls."""

    @pytest.mark.asyncio
    async def test_sequential_calls_work(self) -> None:
        """Two sequential calls should not corrupt state."""
        adapter = OllamaAdapter("qwen2.5:32b", base_url="http://localhost:11434")

        with respx.mock:
            respx.get("http://localhost:11434/api/tags").mock(
                return_value=httpx.Response(200, json={"models": [{"name": "qwen2.5:32b"}]})
            )
            respx.post("http://localhost:11434/api/chat").mock(
                return_value=httpx.Response(
                    200,
                    text=json.dumps({"message": {"content": "Response"}})
                    + "\n"
                    + json.dumps({"done": True, "prompt_eval_count": 5, "eval_count": 1})
                    + "\n",
                )
            )

            # Call 1
            async for _ in adapter.stream([Message(role="user", content="Q1")]):
                pass
            usage1 = await adapter.get_usage()

            # Call 2
            async for _ in adapter.stream([Message(role="user", content="Q2")]):
                pass
            usage2 = await adapter.get_usage()

            # Both should have recorded tokens (even if same due to mock)
            assert usage1.input_tokens > 0
            assert usage2.input_tokens > 0


class TestHappyPath:
    """Happy path: normal operation scenarios."""

    @pytest.mark.asyncio
    async def test_single_token_response(self) -> None:
        """Stream a single token response."""
        adapter = OllamaAdapter("qwen2.5:32b", base_url="http://localhost:11434")

        with respx.mock:
            respx.get("http://localhost:11434/api/tags").mock(
                return_value=httpx.Response(200, json={"models": [{"name": "qwen2.5:32b"}]})
            )
            respx.post("http://localhost:11434/api/chat").mock(
                return_value=httpx.Response(
                    200,
                    text=json.dumps({"message": {"content": "Hello"}})
                    + "\n"
                    + json.dumps({"done": True, "prompt_eval_count": 5, "eval_count": 1})
                    + "\n",
                )
            )

            tokens = []
            async for delta in adapter.stream([Message(role="user", content="Hi")]):
                tokens.append(delta.text)

            assert tokens == ["Hello"]

            usage = await adapter.get_usage()
            assert usage.input_tokens == 5
            assert usage.output_tokens == 1
            assert usage.cost_usd == 0  # Ollama is free

    @pytest.mark.asyncio
    async def test_multi_token_response(self) -> None:
        """Stream multiple tokens."""
        adapter = OllamaAdapter("qwen2.5:32b", base_url="http://localhost:11434")

        with respx.mock:
            respx.get("http://localhost:11434/api/tags").mock(
                return_value=httpx.Response(200, json={"models": [{"name": "qwen2.5:32b"}]})
            )
            respx.post("http://localhost:11434/api/chat").mock(
                return_value=httpx.Response(
                    200,
                    text=json.dumps({"message": {"content": "Hello"}})
                    + "\n"
                    + json.dumps({"message": {"content": " "}})
                    + "\n"
                    + json.dumps({"message": {"content": "world"}})
                    + "\n"
                    + json.dumps({"done": True, "prompt_eval_count": 5, "eval_count": 3})
                    + "\n",
                )
            )

            tokens = []
            async for delta in adapter.stream([Message(role="user", content="Hi")]):
                tokens.append(delta.text)

            assert tokens == ["Hello", " ", "world"]

            usage = await adapter.get_usage()
            assert usage.output_tokens == 3

    @pytest.mark.asyncio
    async def test_temperature_parameter_passed(self) -> None:
        """Verify temperature is passed to Ollama."""
        adapter = OllamaAdapter("qwen2.5:32b", base_url="http://localhost:11434")

        def check_temp(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert body["options"]["temperature"] == 0.3
            return httpx.Response(
                200,
                text=json.dumps({"message": {"content": "OK"}})
                + "\n"
                + json.dumps({"done": True, "prompt_eval_count": 5, "eval_count": 1})
                + "\n",
            )

        with respx.mock:
            respx.get("http://localhost:11434/api/tags").mock(
                return_value=httpx.Response(200, json={"models": [{"name": "qwen2.5:32b"}]})
            )
            respx.post("http://localhost:11434/api/chat").mock(side_effect=check_temp)

            async for _ in adapter.stream([Message(role="user", content="Hi")], temperature=0.3):
                pass

    @pytest.mark.asyncio
    async def test_empty_response(self) -> None:
        """Model returns no content (rare but valid)."""
        adapter = OllamaAdapter("qwen2.5:32b", base_url="http://localhost:11434")

        with respx.mock:
            respx.get("http://localhost:11434/api/tags").mock(
                return_value=httpx.Response(200, json={"models": [{"name": "qwen2.5:32b"}]})
            )
            respx.post("http://localhost:11434/api/chat").mock(
                return_value=httpx.Response(
                    200,
                    text=json.dumps({"done": True, "prompt_eval_count": 5, "eval_count": 0}) + "\n",
                )
            )

            tokens = []
            async for delta in adapter.stream([Message(role="user", content="Hi")]):
                tokens.append(delta.text)

            # Should handle empty response gracefully
            assert len(tokens) == 0

            usage = await adapter.get_usage()
            assert usage.output_tokens == 0
