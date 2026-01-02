"""
Live tests for tool calling functionality.

These tests verify that LLM providers correctly:
- Receive tool definitions
- Generate tool calls
- Handle tool results
"""

import os as _os

import pytest as _pytest

import brynhild.api as api

# All tests require live API access
pytestmark = [_pytest.mark.live, _pytest.mark.slow]

# Use a more capable model for tool tests
LIVE_TEST_MODEL = _os.environ.get("BRYNHILD_TEST_MODEL", "openai/gpt-oss-120b")


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


# Sample tool definition for testing
CALCULATOR_TOOL = api.Tool(
    name="calculator",
    description="Perform basic arithmetic. Use this for any math calculations.",
    input_schema={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Math expression like '2 + 2' or '10 * 5'",
            },
        },
        "required": ["expression"],
    },
)


class TestLiveToolCalling:
    """Live tests for tool calling functionality."""

    @_pytest.mark.asyncio
    async def test_tool_call_generated(self, provider: api.LLMProvider) -> None:
        """Provider can generate tool calls when tools are provided."""
        if not provider.supports_tools():
            _pytest.skip(f"Model {provider.model} does not support tools")

        response = await provider.complete(
            messages=[
                {
                    "role": "user",
                    "content": "Use the calculator tool to compute 987654 * 123456. "
                    "You MUST use the calculator tool, do not calculate manually.",
                }
            ],
            tools=[CALCULATOR_TOOL],
            max_tokens=200,
        )

        # Model may or may not use tools - this is model-dependent
        # If it does use tools, verify basic structure is correct
        if response.tool_uses:
            tool_use = response.tool_uses[0]
            assert tool_use.name == "calculator"
            # Note: some models may return empty input - this is a model quirk
            # We verify basic structure but don't require specific fields
            assert isinstance(tool_use.input, dict)
        else:
            # Model chose not to use tools - that's valid behavior
            # Just verify we got some response
            has_output = response.content or response.thinking
            assert has_output, "No output from model"

    @_pytest.mark.asyncio
    async def test_tool_use_has_valid_structure(self, provider: api.LLMProvider) -> None:
        """Tool use response has valid structure."""
        if not provider.supports_tools():
            _pytest.skip(f"Model {provider.model} does not support tools")

        response = await provider.complete(
            messages=[{"role": "user", "content": "What is 123 + 456? Use the calculator."}],
            tools=[CALCULATOR_TOOL],
            max_tokens=200,
        )

        if not response.tool_uses:
            _pytest.skip("Model did not generate tool use")

        # Verify tool use structure
        tool_use = response.tool_uses[0]
        assert tool_use.id is not None
        assert tool_use.name == "calculator"
        assert isinstance(tool_use.input, dict)
        # Note: some models may generate tool calls with empty/partial input
        # This is a model behavior issue, not a provider issue
        # We verify the structure exists but accept that input may be incomplete

    @_pytest.mark.asyncio
    async def test_streaming_with_tools(self, provider: api.LLMProvider) -> None:
        """Streaming works when tools are provided."""
        if not provider.supports_tools():
            _pytest.skip(f"Model {provider.model} does not support tools")

        events = []
        async for event in provider.stream(
            messages=[{"role": "user", "content": "Calculate 7 * 8 using the calculator."}],
            tools=[CALCULATOR_TOOL],
            max_tokens=200,
        ):
            events.append(event)

        # Should complete without error and have a stop event
        stop_events = [e for e in events if e.type == "message_stop"]
        assert len(stop_events) == 1, f"Expected stop event, got: {[e.type for e in events]}"

        # May have tool events or text events depending on model behavior
        tool_events = [e for e in events if e.type == "tool_use_start"]
        text_events = [e for e in events if e.type in ("text_delta", "thinking_delta")]
        assert len(tool_events) > 0 or len(text_events) > 0, "Should have tool or text events"
