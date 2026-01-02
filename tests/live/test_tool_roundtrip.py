"""
Live test for complete tool call round-trip.

Tests that tool results are properly received by the model after
the fix for missing assistant tool_calls messages.
"""

import os as _os

import pytest as _pytest

import brynhild.api as api
import brynhild.core.types as core_types
import brynhild.tools.base as tools_base

pytestmark = [_pytest.mark.live, _pytest.mark.slow]

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


CALCULATOR_TOOL = api.Tool(
    name="calculator",
    description="Perform math calculations. Always use this for arithmetic.",
    input_schema={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Math expression like '2 + 2'",
            },
        },
        "required": ["expression"],
    },
)


class TestToolRoundTrip:
    """Test complete tool call -> result -> response flow."""

    @_pytest.mark.asyncio
    async def test_tool_result_received_by_model(self, provider: api.LLMProvider) -> None:
        """Model receives and uses tool result after our message format fix."""
        if not provider.supports_tools():
            _pytest.skip(f"Model {provider.model} does not support tools")

        # Step 1: Get model to call the calculator
        response1 = await provider.complete(
            messages=[
                {
                    "role": "user",
                    "content": "Use the calculator tool to compute 12345 * 67890. "
                    "You MUST use the calculator tool.",
                }
            ],
            tools=[CALCULATOR_TOOL],
            max_tokens=200,
        )

        if not response1.tool_uses:
            _pytest.skip("Model did not generate tool call")

        tool_use = response1.tool_uses[0]
        assert tool_use.name == "calculator"

        # Step 2: Build proper message sequence with:
        # - Original user message
        # - Assistant message with tool_calls (our fix adds this)
        # - Tool result message (our fix sends these individually)
        assistant_msg = core_types.format_assistant_tool_call([tool_use], response1.content or "")

        # Simulate calculator result
        fake_result = tools_base.ToolResult(success=True, output="838102050", error=None)
        tool_result_msg = core_types.format_tool_result_message(tool_use.id, fake_result)

        messages = [
            {
                "role": "user",
                "content": "Use the calculator tool to compute 12345 * 67890. "
                "You MUST use the calculator tool.",
            },
            assistant_msg,
            tool_result_msg,
        ]

        # Step 3: Send with tool result - model should respond with the answer
        response2 = await provider.complete(
            messages=messages,
            tools=[CALCULATOR_TOOL],
            max_tokens=200,
        )

        # Model should either:
        # 1. Include the result in its response (success!)
        # 2. NOT call the calculator again (would indicate infinite loop bug)
        if response2.tool_uses:
            # Model called another tool - check if it's the same call (bad)
            for tu in response2.tool_uses:
                if tu.name == "calculator":
                    _pytest.fail(
                        "Model called calculator again - indicates infinite loop bug. "
                        "Tool result was not properly received."
                    )

        # Success - model gave a response instead of looping
        assert response2.content, "Model should give a text response after tool result"
        # The response should reference the calculation result
        # (either the exact number or acknowledge the calculation)
        print(f"Model response after tool result: {response2.content}")

    @_pytest.mark.asyncio
    async def test_message_format_structure(self, provider: api.LLMProvider) -> None:
        """Verify the message format structure is correct."""
        if not provider.supports_tools():
            _pytest.skip(f"Model {provider.model} does not support tools")

        # Get a tool call
        response = await provider.complete(
            messages=[{"role": "user", "content": "Calculate 2+2 using the calculator."}],
            tools=[CALCULATOR_TOOL],
            max_tokens=100,
        )

        if not response.tool_uses:
            _pytest.skip("Model did not generate tool call")

        tool_use = response.tool_uses[0]

        # Verify assistant message format
        assistant_msg = core_types.format_assistant_tool_call([tool_use], "")
        assert assistant_msg["role"] == "assistant"
        assert "tool_calls" in assistant_msg
        assert len(assistant_msg["tool_calls"]) == 1
        assert assistant_msg["tool_calls"][0]["id"] == tool_use.id
        assert assistant_msg["tool_calls"][0]["type"] == "function"
        assert assistant_msg["tool_calls"][0]["function"]["name"] == tool_use.name

        # Verify tool result message format
        result = tools_base.ToolResult(success=True, output="4", error=None)
        tool_result_msg = core_types.format_tool_result_message(tool_use.id, result)
        assert tool_result_msg["role"] == "tool_result"
        assert tool_result_msg["tool_use_id"] == tool_use.id
        assert tool_result_msg["content"] == "4"
        assert tool_result_msg["is_error"] is False
