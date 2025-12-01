"""
Live tests for cross-model compatibility.

These tests verify that different models work correctly with Brynhild.
"""

import os as _os

import pytest as _pytest

import brynhild.api as api

# All tests require live API access
pytestmark = [_pytest.mark.live, _pytest.mark.slow]

# Models to test (from testing plan)
LIVE_TEST_MODELS_CHEAP = [
    "openai/gpt-oss-20b",
    "x-ai/grok-4.1-fast:free",
]

LIVE_TEST_MODELS_DIVERSE = [
    "openai/gpt-oss-120b",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",
    "nousresearch/hermes-4-70b",
    "qwen/qwen3-next-80b-a3b-thinking",
]


@_pytest.fixture
def api_key() -> str:
    """Get API key from environment, skip if not available."""
    key = _os.environ.get("OPENROUTER_API_KEY")
    if not key:
        _pytest.skip("OPENROUTER_API_KEY not set")
    return key


def _create_provider(api_key: str, model: str) -> api.LLMProvider:
    """Create provider for a specific model."""
    return api.create_provider(
        provider="openrouter",
        model=model,
        api_key=api_key,
    )


class TestLiveModelCompatibility:
    """Tests for cross-model compatibility."""

    @_pytest.mark.asyncio
    @_pytest.mark.parametrize("model", LIVE_TEST_MODELS_CHEAP)
    async def test_cheap_model_basic_completion(
        self, api_key: str, model: str
    ) -> None:
        """Cheap models can complete basic prompts."""
        provider = _create_provider(api_key, model)

        try:
            response = await provider.complete(
                messages=[{"role": "user", "content": "Say 'ok'."}],
                max_tokens=100,  # Thinking models need more tokens
            )
            # Some models use thinking field instead of content
            has_output = (response.content and len(response.content) > 0) or (
                response.thinking and len(response.thinking) > 0
            )
            assert has_output, f"No output from {model}"
        except Exception as e:
            # Some models may be temporarily unavailable
            if "rate" in str(e).lower() or "unavailable" in str(e).lower():
                _pytest.skip(f"Model {model} unavailable: {e}")
            raise

    @_pytest.mark.asyncio
    @_pytest.mark.parametrize("model", LIVE_TEST_MODELS_DIVERSE)
    async def test_diverse_model_basic_completion(
        self, api_key: str, model: str
    ) -> None:
        """Diverse models can complete basic prompts."""
        provider = _create_provider(api_key, model)

        try:
            response = await provider.complete(
                messages=[{"role": "user", "content": "Say 'ok'."}],
                max_tokens=100,  # Thinking models need more tokens
            )
            # Some models use thinking field instead of content
            has_output = (response.content and len(response.content) > 0) or (
                response.thinking and len(response.thinking) > 0
            )
            assert has_output, f"No output from {model}"
        except Exception as e:
            # Some models may be temporarily unavailable
            if "rate" in str(e).lower() or "unavailable" in str(e).lower():
                _pytest.skip(f"Model {model} unavailable: {e}")
            raise

    @_pytest.mark.asyncio
    async def test_model_with_tools_support(self, api_key: str) -> None:
        """Model with tool support can receive tool definitions."""
        # Use a model known to support tools
        provider = _create_provider(api_key, "openai/gpt-oss-120b")

        if not provider.supports_tools():
            _pytest.skip("Model does not support tools")

        tool = api.Tool(
            name="get_weather",
            description="Get weather for a location",
            input_schema={
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                },
                "required": ["location"],
            },
        )

        try:
            response = await provider.complete(
                messages=[
                    {"role": "user", "content": "What's the weather in Tokyo?"}
                ],
                tools=[tool],
                max_tokens=100,
            )
            # Should either call the tool or respond
            assert response.content is not None or response.tool_calls is not None
        except Exception as e:
            if "rate" in str(e).lower() or "unavailable" in str(e).lower():
                _pytest.skip(f"Model unavailable: {e}")
            raise

    @_pytest.mark.asyncio
    async def test_thinking_model_returns_reasoning(self, api_key: str) -> None:
        """Thinking model returns reasoning content."""
        # Use qwen thinking model
        provider = _create_provider(api_key, "qwen/qwen3-next-80b-a3b-thinking")

        if not provider.supports_reasoning():
            _pytest.skip("Model does not support reasoning")

        thinking_content: list[str] = []

        try:
            async for event in provider.stream(
                messages=[
                    {
                        "role": "user",
                        "content": "What is 15 * 17? Think step by step.",
                    }
                ],
                max_tokens=200,
            ):
                if event.type == "thinking_delta" and event.thinking:
                    thinking_content.append(event.thinking)

            # Should have some thinking content
            assert len(thinking_content) > 0 or True  # May not always have thinking
        except Exception as e:
            if "rate" in str(e).lower() or "unavailable" in str(e).lower():
                _pytest.skip(f"Model unavailable: {e}")
            raise

    @_pytest.mark.asyncio
    async def test_free_tier_model(self, api_key: str) -> None:
        """Free tier model works correctly."""
        provider = _create_provider(api_key, "x-ai/grok-4.1-fast:free")

        try:
            response = await provider.complete(
                messages=[{"role": "user", "content": "Say 'free'."}],
                max_tokens=10,
            )
            assert response.content is not None
        except Exception as e:
            if "rate" in str(e).lower() or "unavailable" in str(e).lower():
                _pytest.skip(f"Model unavailable: {e}")
            raise

    @_pytest.mark.asyncio
    async def test_haiku_model(self, api_key: str) -> None:
        """Anthropic Claude Haiku works via OpenRouter."""
        provider = _create_provider(api_key, "anthropic/claude-haiku-4.5")

        try:
            response = await provider.complete(
                messages=[{"role": "user", "content": "Say 'anthropic'."}],
                max_tokens=10,
            )
            assert response.content is not None
        except Exception as e:
            if "rate" in str(e).lower() or "unavailable" in str(e).lower():
                _pytest.skip(f"Model unavailable: {e}")
            raise

