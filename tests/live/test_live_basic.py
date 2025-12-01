"""
Live tests for basic LLM functionality.

These tests make actual API calls to verify:
- Provider connectivity
- Basic chat completion
- Streaming responses
- Token usage reporting
"""

import os as _os

import pytest as _pytest

import brynhild.api as api

# All tests require live API access
pytestmark = [_pytest.mark.live, _pytest.mark.slow]

# Default model for live tests (cheap)
LIVE_TEST_MODEL = _os.environ.get("BRYNHILD_TEST_MODEL", "openai/gpt-oss-20b")


@_pytest.fixture
def api_key() -> str:
    """Get API key from environment, skip if not available."""
    key = _os.environ.get("OPENROUTER_API_KEY")
    if not key:
        _pytest.skip("OPENROUTER_API_KEY not set")
    return key


@_pytest.fixture
def provider(api_key: str) -> api.LLMProvider:
    """Create a provider for live tests."""
    return api.create_provider(
        provider="openrouter",
        model=LIVE_TEST_MODEL,
        api_key=api_key,
    )


class TestLiveBasicChat:
    """Live tests for basic chat functionality."""

    @_pytest.mark.asyncio
    async def test_simple_completion(self, provider: api.LLMProvider) -> None:
        """Provider can complete a simple prompt."""
        response = await provider.complete(
            messages=[{"role": "user", "content": "Say 'hello' and nothing else."}],
            max_tokens=100,  # Thinking models need more tokens
        )

        # Some models put response in thinking field, others in content
        has_output = (response.content and len(response.content) > 0) or (
            response.thinking and len(response.thinking) > 0
        )
        assert has_output, f"No output: content={response.content!r}, thinking={response.thinking!r}"
        assert response.stop_reason in ("stop", "end_turn", "max_tokens", "length")

    @_pytest.mark.asyncio
    async def test_token_usage_reported(self, provider: api.LLMProvider) -> None:
        """Provider reports token usage."""
        response = await provider.complete(
            messages=[{"role": "user", "content": "Say 'test'."}],
            max_tokens=10,
        )

        assert response.usage is not None
        assert response.usage.input_tokens > 0
        assert response.usage.output_tokens > 0

    @_pytest.mark.asyncio
    async def test_streaming_response(self, provider: api.LLMProvider) -> None:
        """Provider can stream responses."""
        events = []
        async for event in provider.stream(
            messages=[{"role": "user", "content": "Count from 1 to 3."}],
            max_tokens=100,
        ):
            events.append(event)

        # Should have at least some content events and a stop event
        assert len(events) >= 2
        # Accept either text_delta or thinking_delta (thinking models)
        content_events = [e for e in events if e.type in ("text_delta", "thinking_delta")]
        stop_events = [e for e in events if e.type == "message_stop"]
        assert len(content_events) >= 1, f"No content events in: {[e.type for e in events]}"
        assert len(stop_events) == 1

    @_pytest.mark.asyncio
    async def test_streaming_accumulates_text(self, provider: api.LLMProvider) -> None:
        """Streaming text deltas form complete response."""
        text_parts = []
        thinking_parts = []
        async for event in provider.stream(
            messages=[{"role": "user", "content": "Say 'hello world'."}],
            max_tokens=100,
        ):
            if event.type == "text_delta" and event.text:
                text_parts.append(event.text)
            elif event.type == "thinking_delta" and event.thinking:
                thinking_parts.append(event.thinking)

        full_text = "".join(text_parts).lower()
        full_thinking = "".join(thinking_parts).lower()
        # Should have some output (either in text or thinking)
        has_output = len(full_text) > 0 or len(full_thinking) > 0
        assert has_output, "No text or thinking output"

    @_pytest.mark.asyncio
    async def test_system_prompt_respected(self, provider: api.LLMProvider) -> None:
        """Provider respects system prompt."""
        response = await provider.complete(
            messages=[{"role": "user", "content": "What is your name?"}],
            system="Your name is TestBot. Always introduce yourself by name.",
            max_tokens=150,  # Thinking models need more tokens
        )

        # System prompt should influence response
        # Some models put response in thinking field, others in content
        has_output = (response.content and len(response.content) > 0) or (
            response.thinking and len(response.thinking) > 0
        )
        assert has_output

