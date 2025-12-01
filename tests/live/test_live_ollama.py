"""
Live tests for Ollama provider.

These tests make actual API calls to an Ollama server.

Configuration (set in .env, which is gitignored):
    BRYNHILD_OLLAMA_HOST: Hostname of Ollama server (preferred)
    OLLAMA_HOST: Fallback if BRYNHILD_OLLAMA_HOST not set (standard Ollama convention)
    BRYNHILD_OLLAMA_MODEL: Model to use for testing (default: openai/gpt-oss-120b)

Example usage:
    # Run with settings from .env
    make test-ollama

    # Or manually with environment variables
    BRYNHILD_OLLAMA_HOST=myserver ./local.venv/bin/pytest tests/live/test_live_ollama.py -v
"""

import os as _os

import pytest as _pytest

import brynhild.api as api
import brynhild.api.ollama_provider as ollama_provider

# All tests require live Ollama access
# ollama_local: runs against local/private Ollama server (set BRYNHILD_OLLAMA_HOST in .env)
pytestmark = [_pytest.mark.live, _pytest.mark.slow, _pytest.mark.ollama, _pytest.mark.ollama_local]

# Default model for Ollama live tests (canonical OpenRouter format, translated by provider)
OLLAMA_TEST_MODEL = _os.environ.get("BRYNHILD_OLLAMA_MODEL", "openai/gpt-oss-120b")


@_pytest.fixture
def provider() -> ollama_provider.OllamaProvider:
    """Create an Ollama provider for live tests (with profile auto-attached)."""
    # Use factory to get profile auto-attached
    return api.create_provider(  # type: ignore[return-value]
        provider="ollama",
        model=OLLAMA_TEST_MODEL,
    )


class TestOllamaConnection:
    """Test basic Ollama server connectivity."""

    @_pytest.mark.asyncio
    async def test_list_models(self, provider: ollama_provider.OllamaProvider) -> None:
        """Can list available models on the server."""
        models = await provider.list_models()

        # Should return a list (may be empty if no models pulled)
        assert isinstance(models, list)

        # If models exist, check structure
        if models:
            model = models[0]
            assert "name" in model

    @_pytest.mark.asyncio
    async def test_connection_info(self, provider: ollama_provider.OllamaProvider) -> None:
        """Provider reports correct connection info."""
        assert provider.name == "ollama"
        assert provider.model == OLLAMA_TEST_MODEL
        # Base URL should be set
        assert provider.base_url.startswith("http")


class TestOllamaBasicChat:
    """Live tests for basic chat functionality with Ollama."""

    @_pytest.mark.asyncio
    async def test_simple_completion(self, provider: ollama_provider.OllamaProvider) -> None:
        """Provider can complete a simple prompt."""
        response = await provider.complete(
            messages=[{"role": "user", "content": "Say 'hello' and nothing else."}],
            max_tokens=100,
        )

        assert response.content is not None
        assert len(response.content) > 0
        assert response.stop_reason in ("stop", "end_turn", "length", None)

    @_pytest.mark.asyncio
    async def test_token_usage_reported(self, provider: ollama_provider.OllamaProvider) -> None:
        """Provider reports token usage."""
        response = await provider.complete(
            messages=[{"role": "user", "content": "Say 'test'."}],
            max_tokens=50,
        )

        # Ollama should report usage
        assert response.usage is not None
        assert response.usage.input_tokens > 0
        assert response.usage.output_tokens > 0

    @_pytest.mark.asyncio
    async def test_streaming_response(self, provider: ollama_provider.OllamaProvider) -> None:
        """Provider can stream responses."""
        events = []
        async for event in provider.stream(
            messages=[{"role": "user", "content": "Count from 1 to 3."}],
            max_tokens=100,
        ):
            events.append(event)

        # Should have at least start, some content, and stop events
        assert len(events) >= 2
        event_types = [e.type for e in events]
        assert "message_start" in event_types
        assert "message_stop" in event_types

    @_pytest.mark.asyncio
    async def test_streaming_accumulates_text(
        self, provider: ollama_provider.OllamaProvider
    ) -> None:
        """Streaming text deltas form complete response."""
        text_parts = []
        async for event in provider.stream(
            messages=[{"role": "user", "content": "Say 'hello world'."}],
            max_tokens=100,
        ):
            if event.type == "text_delta" and event.text:
                text_parts.append(event.text)

        full_text = "".join(text_parts).lower()
        assert len(full_text) > 0

    @_pytest.mark.asyncio
    async def test_system_prompt_respected(
        self, provider: ollama_provider.OllamaProvider
    ) -> None:
        """Provider respects system prompt."""
        response = await provider.complete(
            messages=[{"role": "user", "content": "What is your name?"}],
            system="Your name is TestBot. Always introduce yourself by name.",
            max_tokens=150,
        )

        assert response.content is not None
        assert len(response.content) > 0


class TestOllamaMultiTurn:
    """Test multi-turn conversation with Ollama."""

    @_pytest.mark.asyncio
    async def test_multi_turn_conversation(
        self, provider: ollama_provider.OllamaProvider
    ) -> None:
        """Provider maintains context across turns."""
        messages = [
            {"role": "user", "content": "My favorite color is blue. Remember that."},
        ]

        # First turn
        response1 = await provider.complete(messages=messages, max_tokens=100)
        assert response1.content

        # Add assistant response and follow-up
        messages.append({"role": "assistant", "content": response1.content})
        messages.append({"role": "user", "content": "What is my favorite color?"})

        # Second turn - should remember from conversation, not search
        response2 = await provider.complete(messages=messages, max_tokens=100)
        assert response2.content
        # Model should reference blue in some way
        assert "blue" in response2.content.lower()


class TestOllamaFactory:
    """Test creating Ollama provider via factory."""

    @_pytest.mark.asyncio
    async def test_create_via_factory(self) -> None:
        """Can create Ollama provider via factory."""
        provider = api.create_provider(
            provider="ollama",
            model=OLLAMA_TEST_MODEL,
        )

        assert provider.name == "ollama"
        assert provider.model == OLLAMA_TEST_MODEL

        # Basic connectivity test
        response = await provider.complete(
            messages=[{"role": "user", "content": "Say 'ok'."}],
            max_tokens=50,
        )
        assert response.content

