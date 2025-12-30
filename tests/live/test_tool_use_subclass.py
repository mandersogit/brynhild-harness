"""
Live test for ToolUse subclass with custom fields.

Verifies that custom fields added via to_tool_call_dict() override
survive the round-trip through message history to a real model.
"""

import dataclasses as _dataclasses
import json as _json
import os as _os
import pathlib as _pathlib
import tempfile as _tempfile
import typing as _typing

import pytest as _pytest

import brynhild.api as api
import brynhild.api.types as api_types
import brynhild.core.types as core_types
import brynhild.logging.conversation_logger as conversation_logger
import brynhild.tools.base as tools_base

pytestmark = [_pytest.mark.live, _pytest.mark.slow]

LIVE_TEST_MODEL = _os.environ.get("BRYNHILD_TEST_MODEL", "openai/gpt-oss-120b")


@_dataclasses.dataclass
class GeminiStyleToolUse(api_types.ToolUse):
    """
    Subclass simulating Gemini's thought_signature pattern.

    This mimics what CEGAI would implement for Gemini 3 support.
    """

    thought_signature: str | None = None

    def to_tool_call_dict(self) -> dict[str, _typing.Any]:
        d = super().to_tool_call_dict()
        if self.thought_signature:
            d["thought_signature"] = self.thought_signature
        return d


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


class TestToolUseSubclassRoundTrip:
    """Test that custom ToolUse subclass fields survive round-trip to real model."""

    @_pytest.mark.asyncio
    async def test_custom_field_in_message_sent_to_model(
        self, provider: api.LLMProvider
    ) -> None:
        """
        Verify custom fields from ToolUse subclass appear in message history
        and the model accepts the message without error.

        This simulates the Gemini thought_signature pattern:
        1. Provider returns ToolUse subclass with custom field
        2. format_assistant_tool_call() serializes it (including custom field)
        3. Message with custom field is sent back to model
        4. Model responds normally (accepts the extra field)
        """
        if not provider.supports_tools():
            _pytest.skip(f"Model {provider.model} does not support tools")

        # Step 1: Get model to call a tool
        response1 = await provider.complete(
            messages=[
                {
                    "role": "user",
                    "content": "Use the calculator tool to compute 7 * 8. "
                    "You MUST use the calculator tool.",
                }
            ],
            tools=[CALCULATOR_TOOL],
            max_tokens=200,
        )

        if not response1.tool_uses:
            _pytest.skip("Model did not generate tool call")

        original_tool_use = response1.tool_uses[0]
        assert original_tool_use.name == "calculator"

        # Step 2: Convert to our custom subclass with a "thought_signature"
        # This simulates what a Gemini provider would do
        custom_tool_use = GeminiStyleToolUse(
            id=original_tool_use.id,
            name=original_tool_use.name,
            input=original_tool_use.input,
            thought_signature="test_sig_abc123_simulated_gemini_signature",
        )

        # Step 3: Format the assistant message - should include our custom field
        assistant_msg = core_types.format_assistant_tool_call(
            [custom_tool_use], response1.content or ""
        )

        # Verify custom field is in the serialized message
        assert "tool_calls" in assistant_msg
        assert len(assistant_msg["tool_calls"]) == 1
        tool_call_dict = assistant_msg["tool_calls"][0]
        assert tool_call_dict["thought_signature"] == "test_sig_abc123_simulated_gemini_signature"
        print(f"✓ Custom field present in tool_call: {tool_call_dict.get('thought_signature')}")

        # Step 4: Create tool result
        fake_result = tools_base.ToolResult(success=True, output="56", error=None)
        tool_result_msg = core_types.format_tool_result_message(
            custom_tool_use.id, fake_result
        )

        # Step 5: Send message with custom field back to model
        # If the model rejects the extra field, this would error
        messages = [
            {
                "role": "user",
                "content": "Use the calculator tool to compute 7 * 8. "
                "You MUST use the calculator tool.",
            },
            assistant_msg,  # Contains our custom thought_signature field
            tool_result_msg,
        ]

        response2 = await provider.complete(
            messages=messages,
            tools=[CALCULATOR_TOOL],
            max_tokens=200,
        )

        # Step 6: Verify model responded (didn't reject the message format)
        # Model should give a response incorporating the tool result
        if response2.tool_uses:
            for tu in response2.tool_uses:
                if tu.name == "calculator":
                    _pytest.fail(
                        "Model called calculator again - tool result not received"
                    )

        assert response2.content, "Model should respond after receiving tool result"
        print(f"✓ Model accepted message with custom field and responded: {response2.content[:100]}...")

    @_pytest.mark.asyncio
    async def test_multiple_tool_calls_with_custom_fields(
        self, provider: api.LLMProvider
    ) -> None:
        """
        Test that multiple tool calls can each have their own custom field values.
        """
        if not provider.supports_tools():
            _pytest.skip(f"Model {provider.model} does not support tools")

        # Create multiple tool uses with different signatures
        tool_uses = [
            GeminiStyleToolUse(
                id="call_1",
                name="calculator",
                input={"expression": "1+1"},
                thought_signature="sig_for_call_1",
            ),
            GeminiStyleToolUse(
                id="call_2",
                name="calculator",
                input={"expression": "2+2"},
                thought_signature="sig_for_call_2",
            ),
        ]

        # Format message
        assistant_msg = core_types.format_assistant_tool_call(tool_uses, "")

        # Verify each tool call has its own signature
        assert len(assistant_msg["tool_calls"]) == 2
        assert assistant_msg["tool_calls"][0]["thought_signature"] == "sig_for_call_1"
        assert assistant_msg["tool_calls"][1]["thought_signature"] == "sig_for_call_2"
        print("✓ Multiple tool calls each have their own custom field value")


class TestToolUseSubclassWithLogging:
    """Test that custom ToolUse subclass works with the logging system."""

    @_pytest.mark.asyncio
    async def test_logging_works_with_custom_tool_use_subclass(
        self, provider: api.LLMProvider
    ) -> None:
        """
        Verify that logging works correctly when given a custom ToolUse subclass.

        The logger extracts base fields (name, input, id) from ToolUse objects.
        This test verifies:
        1. Logger doesn't crash with custom subclass
        2. Base fields are logged correctly
        3. Custom field (thought_signature) is NOT in logs (documented limitation)
        """
        if not provider.supports_tools():
            _pytest.skip(f"Model {provider.model} does not support tools")

        # Step 1: Get a real tool call from the model
        response = await provider.complete(
            messages=[
                {
                    "role": "user",
                    "content": "Use the calculator to compute 3 * 4. You MUST use the tool.",
                }
            ],
            tools=[CALCULATOR_TOOL],
            max_tokens=200,
        )

        if not response.tool_uses:
            _pytest.skip("Model did not generate tool call")

        original_tool_use = response.tool_uses[0]

        # Step 2: Convert to custom subclass (simulating Gemini provider)
        custom_tool_use = GeminiStyleToolUse(
            id=original_tool_use.id,
            name=original_tool_use.name,
            input=original_tool_use.input,
            thought_signature="secret_signature_value_12345",
        )

        # Step 3: Create a logger and log the tool call
        # This mimics what _execute_tool() does
        with _tempfile.TemporaryDirectory() as tmpdir:
            log_file = _pathlib.Path(tmpdir) / "test_session.jsonl"
            logger = conversation_logger.ConversationLogger(
                log_file=log_file,
                provider="test",
                model="test-model",
            )

            # Log the tool call - this is what _execute_tool does
            # It extracts fields from the ToolUse object
            logger.log_tool_call(
                tool_name=custom_tool_use.name,
                tool_input=custom_tool_use.input,
                tool_id=custom_tool_use.id,
                call_type="native",
            )

            # Log a tool result too
            logger.log_tool_result(
                tool_name=custom_tool_use.name,
                success=True,
                output="12",
                tool_id=custom_tool_use.id,
            )

            logger.close()

            # Step 4: Read and verify the log
            log_content = log_file.read_text()
            log_lines = [_json.loads(line) for line in log_content.strip().split("\n")]

            # Find the tool_call event
            tool_call_events = [e for e in log_lines if e.get("event_type") == "tool_call"]
            assert len(tool_call_events) == 1
            tool_call_event = tool_call_events[0]

            # Verify base fields are logged (flat structure, not nested under "data")
            assert tool_call_event["tool_name"] == custom_tool_use.name
            assert tool_call_event["tool_input"] == custom_tool_use.input
            assert tool_call_event["tool_id"] == custom_tool_use.id
            print(f"✓ Base fields logged: name={custom_tool_use.name}, id={custom_tool_use.id}")

            # Verify custom field is NOT in the log (documented limitation)
            assert "thought_signature" not in tool_call_event
            assert "thought_signature" not in str(tool_call_event)
            print("✓ Custom field (thought_signature) correctly NOT in log")

            # Find the tool_result event
            tool_result_events = [e for e in log_lines if e.get("event_type") == "tool_result"]
            assert len(tool_result_events) == 1
            assert tool_result_events[0]["success"] is True
            print("✓ Tool result logged correctly")

