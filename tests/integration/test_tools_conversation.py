"""Integration tests for Tools + ConversationProcessor interaction."""

import typing as _typing

import pytest as _pytest

import brynhild.api.types as api_types
import brynhild.core.conversation as conversation
import brynhild.tools.registry as tools_registry
import brynhild.ui.base as ui_base
import tests.conftest as conftest


class RecordingCallbacks(conversation.ConversationCallbacks):
    """Callbacks that record all events for inspection."""

    def __init__(self, grant_permission: bool = True) -> None:
        self.grant_permission = grant_permission
        self.tool_calls: list[ui_base.ToolCallDisplay] = []
        self.tool_results: list[ui_base.ToolResultDisplay] = []
        self.permission_requests: list[ui_base.ToolCallDisplay] = []
        self.events: list[tuple[str, _typing.Any]] = []

    async def on_stream_start(self) -> None:
        pass

    async def on_stream_end(self) -> None:
        pass

    async def on_thinking_delta(self, text: str) -> None:  # noqa: ARG002
        pass

    async def on_thinking_complete(self, full_text: str) -> None:  # noqa: ARG002
        pass

    async def on_text_delta(self, text: str) -> None:  # noqa: ARG002
        pass

    async def on_text_complete(self, full_text: str, thinking: str | None) -> None:  # noqa: ARG002
        pass

    async def on_tool_call(self, tool_call: ui_base.ToolCallDisplay) -> None:
        self.tool_calls.append(tool_call)
        self.events.append(("tool_call", tool_call))

    async def request_tool_permission(
        self,
        tool_call: ui_base.ToolCallDisplay,
    ) -> bool:
        self.permission_requests.append(tool_call)
        self.events.append(("permission_request", tool_call))
        return self.grant_permission

    async def on_tool_result(self, result: ui_base.ToolResultDisplay) -> None:
        self.tool_results.append(result)
        self.events.append(("tool_result", result))

    async def on_round_start(self, round_num: int) -> None:  # noqa: ARG002
        pass

    def is_cancelled(self) -> bool:
        return False


@_pytest.mark.integration
class TestToolsConversationIntegration:
    """Tests for Tools and ConversationProcessor interaction."""

    @_pytest.mark.asyncio
    async def test_registered_tools_available_for_llm(self) -> None:
        """Registered tools are available when calling LLM."""
        # Setup: Registry with multiple tools
        registry = tools_registry.ToolRegistry()
        registry.register(conftest.MockTool(name="Tool1"))
        registry.register(conftest.MockTool(name="Tool2"))

        provider = conftest.MockProvider()
        callbacks = RecordingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
        )

        # Verify: Processor has access to tools (via internal method)
        tools = processor._get_tools_for_api()
        assert tools is not None
        assert len(tools) == 2
        tool_names = {t.name for t in tools}
        assert "Tool1" in tool_names
        assert "Tool2" in tool_names

    @_pytest.mark.asyncio
    async def test_tool_execution_respects_permission_when_required(self) -> None:
        """Tools requiring permission prompt the user via callbacks."""
        # Setup: Tool that requires permission
        tool = conftest.MockTool(name="DangerousTool", requires_permission=True)
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        # Provider requests tool use
        events = [
            api_types.StreamEvent(
                type="tool_use_start",
                tool_use=api_types.ToolUse(id="t1", name="DangerousTool", input={}),
            ),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="tool_use",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="Done"),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        provider = conftest.MockProvider(stream_events=[events, events2])

        # Callbacks that grant permission
        callbacks = RecordingCallbacks(grant_permission=True)

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=False,  # Require permission
        )

        # Execute
        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        # Verify: Permission was requested
        assert len(callbacks.permission_requests) == 1
        assert callbacks.permission_requests[0].tool_name == "DangerousTool"

        # Verify: Tool was executed (permission granted)
        assert tool.call_count == 1

    @_pytest.mark.asyncio
    async def test_tool_permission_denied_skips_execution(self) -> None:
        """When permission is denied, tool is not executed."""
        # Setup: Tool that requires permission
        tool = conftest.MockTool(name="BlockedTool", requires_permission=True)
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        events = [
            api_types.StreamEvent(
                type="tool_use_start",
                tool_use=api_types.ToolUse(id="t1", name="BlockedTool", input={}),
            ),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="tool_use",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="Okay"),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        provider = conftest.MockProvider(stream_events=[events, events2])

        # Callbacks that deny permission
        callbacks = RecordingCallbacks(grant_permission=False)

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=False,
        )

        # Execute
        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        # Verify: Permission was requested but denied
        assert len(callbacks.permission_requests) == 1

        # Verify: Tool was NOT executed
        assert tool.call_count == 0

    @_pytest.mark.asyncio
    async def test_unknown_tool_handled_gracefully(self) -> None:
        """Unknown tool requests are handled without crashing."""
        # Setup: Empty registry (no tools)
        registry = tools_registry.ToolRegistry()

        events = [
            api_types.StreamEvent(
                type="tool_use_start",
                tool_use=api_types.ToolUse(id="t1", name="NonexistentTool", input={}),
            ),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="tool_use",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="I see"),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        provider = conftest.MockProvider(stream_events=[events, events2])
        callbacks = RecordingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
        )

        # Execute - should not crash
        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "use unknown tool"}],
            system_prompt="test",
        )

        # Verify: Response completed (processor handled unknown tool gracefully)
        assert result.response_text == "I see"

        # Verify: Tool use was recorded in result (even if unknown)
        assert len(result.tool_uses) == 1
        assert result.tool_uses[0].name == "NonexistentTool"

    @_pytest.mark.asyncio
    async def test_tool_error_captured_in_result(self) -> None:
        """Tool execution errors are captured in the result."""
        # Setup: Failing tool
        tool = conftest.FailingTool(name="FailTool", error_message="Simulated failure")
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        events = [
            api_types.StreamEvent(
                type="tool_use_start",
                tool_use=api_types.ToolUse(id="t1", name="FailTool", input={}),
            ),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="tool_use",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="Error noted"),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        provider = conftest.MockProvider(stream_events=[events, events2])
        callbacks = RecordingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
        )

        # Execute
        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        # Verify: Processing completed
        assert result.response_text == "Error noted"

        # Verify: Error captured in tool result
        assert len(callbacks.tool_results) == 1
        assert callbacks.tool_results[0].result.success is False
        assert callbacks.tool_results[0].result.error is not None
        assert "Simulated failure" in callbacks.tool_results[0].result.error

    @_pytest.mark.asyncio
    async def test_tool_result_sent_back_to_llm(self) -> None:
        """Tool results are sent back to LLM for continuation."""
        # Setup: Tool that returns specific output
        tool = conftest.MockTool(name="InfoTool", output="The answer is 42")
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        # First response: tool call
        events1 = [
            api_types.StreamEvent(
                type="tool_use_start",
                tool_use=api_types.ToolUse(id="t1", name="InfoTool", input={}),
            ),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="tool_use",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        # Second response: uses tool result
        events2 = [
            api_types.StreamEvent(type="text_delta", text="Based on the tool: 42"),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=50, output_tokens=10),
            ),
        ]

        provider = conftest.MockProvider(stream_events=[events1, events2])
        callbacks = RecordingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
        )

        # Execute
        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "what's the answer?"}],
            system_prompt="test",
        )

        # Verify: Tool was called
        assert tool.call_count == 1

        # Verify: LLM received tool result and continued
        assert "42" in result.response_text

        # Verify: Both tool call and result events fired
        assert len(callbacks.tool_calls) == 1
        assert len(callbacks.tool_results) == 1
        assert callbacks.tool_results[0].result.output == "The answer is 42"

