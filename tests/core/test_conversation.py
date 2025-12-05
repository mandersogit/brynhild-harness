"""Tests for core/conversation.py."""

import typing as _typing

import pytest as _pytest

import brynhild.api.base as api_base
import brynhild.api.types as api_types
import brynhild.core.conversation as conversation
import brynhild.tools.base as tools_base
import brynhild.tools.registry as tools_registry
import brynhild.ui.adapters as ui_adapters
import brynhild.ui.base as ui_base


class MockTool(tools_base.Tool):
    """A mock tool for testing."""

    def __init__(
        self,
        name: str = "MockTool",
        requires_permission: bool = False,
    ) -> None:
        self._name = name
        self._requires_permission = requires_permission

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "A mock tool"

    @property
    def requires_permission(self) -> bool:
        return self._requires_permission

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, input: dict[str, _typing.Any]) -> tools_base.ToolResult:
        return tools_base.ToolResult(
            success=True,
            output=f"executed with {input}",
            error=None,
        )


class MockProvider(api_base.LLMProvider):
    """Mock LLM provider for testing."""

    def __init__(
        self,
        responses: list[api_types.CompletionResponse] | None = None,
        stream_events: list[list[api_types.StreamEvent]] | None = None,
    ) -> None:
        self._responses = responses or []
        self._stream_events = stream_events or []
        self._response_index = 0
        self._stream_index = 0

    @property
    def name(self) -> str:
        return "mock"

    @property
    def model(self) -> str:
        return "mock-model"

    def supports_tools(self) -> bool:
        return True

    def supports_reasoning(self) -> bool:
        return False

    async def complete(
        self,
        messages: list[dict[str, _typing.Any]],  # noqa: ARG002
        *,
        system: str | None = None,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
        tools: list[api_types.Tool] | None = None,  # noqa: ARG002
    ) -> api_types.CompletionResponse:
        if self._response_index < len(self._responses):
            response = self._responses[self._response_index]
            self._response_index += 1
            return response
        return api_types.CompletionResponse(
            id="mock-id",
            content="mock response",
            stop_reason="stop",
            usage=api_types.Usage(input_tokens=10, output_tokens=5),
        )

    async def stream(
        self,
        messages: list[dict[str, _typing.Any]],  # noqa: ARG002
        *,
        system: str | None = None,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
        tools: list[api_types.Tool] | None = None,  # noqa: ARG002
    ) -> _typing.AsyncIterator[api_types.StreamEvent]:
        if self._stream_index < len(self._stream_events):
            events = self._stream_events[self._stream_index]
            self._stream_index += 1
            for event in events:
                yield event
        else:
            yield api_types.StreamEvent(type="text_delta", text="mock response")
            yield api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            )


class MockCallbacks(conversation.ConversationCallbacks):
    """Mock callbacks for testing."""

    def __init__(self, grant_permission: bool = True) -> None:
        self.grant_permission = grant_permission
        self.events: list[tuple[str, _typing.Any]] = []
        self._cancelled = False

    async def on_stream_start(self) -> None:
        self.events.append(("stream_start", None))

    async def on_stream_end(self) -> None:
        self.events.append(("stream_end", None))

    async def on_thinking_delta(self, text: str) -> None:
        self.events.append(("thinking_delta", text))

    async def on_thinking_complete(self, full_text: str) -> None:
        self.events.append(("thinking_complete", full_text))

    async def on_text_delta(self, text: str) -> None:
        self.events.append(("text_delta", text))

    async def on_text_complete(self, full_text: str, thinking: str | None) -> None:
        self.events.append(("text_complete", (full_text, thinking)))

    async def on_tool_call(self, tool_call: ui_base.ToolCallDisplay) -> None:
        self.events.append(("tool_call", tool_call))

    async def request_tool_permission(
        self,
        tool_call: ui_base.ToolCallDisplay,
    ) -> bool:
        self.events.append(("permission_request", tool_call))
        return self.grant_permission

    async def on_tool_result(self, result: ui_base.ToolResultDisplay) -> None:
        self.events.append(("tool_result", result))

    async def on_round_start(self, round_num: int) -> None:
        self.events.append(("round_start", round_num))

    def is_cancelled(self) -> bool:
        return self._cancelled


class TestConversationResult:
    """Tests for ConversationResult dataclass."""

    def test_create_result(self) -> None:
        """Can create a ConversationResult."""
        result = conversation.ConversationResult(
            response_text="hello",
            thinking="thought about it",
            tool_uses=[],
            tool_results=[],
            input_tokens=10,
            output_tokens=5,
            stop_reason="stop",
        )
        assert result.response_text == "hello"
        assert result.thinking == "thought about it"
        assert result.cancelled is False

    def test_cancelled_flag(self) -> None:
        """Cancelled flag works."""
        result = conversation.ConversationResult(
            response_text="",
            thinking=None,
            tool_uses=[],
            tool_results=[],
            input_tokens=0,
            output_tokens=0,
            stop_reason="cancelled",
            cancelled=True,
        )
        assert result.cancelled is True


class TestConversationProcessor:
    """Tests for ConversationProcessor."""

    @_pytest.mark.asyncio
    async def test_process_streaming_simple(self) -> None:
        """Simple streaming response works."""
        provider = MockProvider()
        callbacks = MockCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "hello"}],
            system_prompt="You are helpful.",
        )

        assert result.response_text == "mock response"
        assert result.cancelled is False

        # Check callbacks were called
        event_types = [e[0] for e in callbacks.events]
        assert "stream_start" in event_types
        assert "stream_end" in event_types
        assert "text_delta" in event_types
        assert "text_complete" in event_types

    @_pytest.mark.asyncio
    async def test_process_streaming_with_thinking(self) -> None:
        """Streaming with thinking works."""
        events = [
            api_types.StreamEvent(type="thinking_delta", thinking="let me think"),
            api_types.StreamEvent(type="thinking_delta", thinking="...more"),
            api_types.StreamEvent(type="text_delta", text="answer"),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        provider = MockProvider(stream_events=[events])
        callbacks = MockCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "hello"}],
            system_prompt="You are helpful.",
        )

        assert result.response_text == "answer"
        # Thinking is set via the callback mechanism, check callbacks were called
        event_types = [e[0] for e in callbacks.events]
        assert "thinking_delta" in event_types
        assert "thinking_complete" in event_types

        # Verify thinking_complete received the full text
        thinking_complete_events = [e for e in callbacks.events if e[0] == "thinking_complete"]
        assert len(thinking_complete_events) == 1
        assert thinking_complete_events[0][1] == "let me think...more"

    @_pytest.mark.asyncio
    async def test_process_streaming_with_tool_use(self) -> None:
        """Streaming with tool use works."""
        tool = MockTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        # First response: tool call
        events1 = [
            api_types.StreamEvent(type="text_delta", text="I'll check"),
            api_types.StreamEvent(
                type="tool_use_start",
                tool_use=api_types.ToolUse(id="t1", name="MockTool", input={}),
            ),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="tool_use",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        # Second response: final answer
        events2 = [
            api_types.StreamEvent(type="text_delta", text="The result is done"),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]

        provider = MockProvider(stream_events=[events1, events2])
        callbacks = MockCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "do something"}],
            system_prompt="You are helpful.",
        )

        assert result.response_text == "The result is done"
        assert len(result.tool_uses) == 1
        assert len(result.tool_results) == 1

        # Check tool callbacks
        event_types = [e[0] for e in callbacks.events]
        assert "tool_call" in event_types
        assert "tool_result" in event_types

    @_pytest.mark.asyncio
    async def test_process_complete_simple(self) -> None:
        """Simple complete response works."""
        provider = MockProvider()
        callbacks = MockCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
        )

        result = await processor.process_complete(
            messages=[{"role": "user", "content": "hello"}],
            system_prompt="You are helpful.",
        )

        assert result.response_text == "mock response"
        assert result.cancelled is False

    @_pytest.mark.asyncio
    async def test_tool_result_display_correct_format(self) -> None:
        """Tool result display uses correct ToolResultDisplay format."""
        tool = MockTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)

        events = [
            api_types.StreamEvent(
                type="tool_use_start",
                tool_use=api_types.ToolUse(id="t1", name="MockTool", input={}),
            ),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="tool_use",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]
        events2 = [
            api_types.StreamEvent(type="text_delta", text="done"),
            api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            ),
        ]

        provider = MockProvider(stream_events=[events, events2])
        callbacks = MockCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
        )

        # Find the tool_result event
        tool_result_events = [e for e in callbacks.events if e[0] == "tool_result"]
        assert len(tool_result_events) == 1

        result_display = tool_result_events[0][1]
        assert isinstance(result_display, ui_base.ToolResultDisplay)
        assert result_display.tool_name == "MockTool"
        assert isinstance(result_display.result, tools_base.ToolResult)
        assert result_display.result.success is True


class TestRendererCallbacks:
    """Tests for RendererCallbacks adapter."""

    def test_init(self) -> None:
        """Can create RendererCallbacks."""
        import io as _io

        import brynhild.ui.plain as plain

        output = _io.StringIO()
        renderer = plain.PlainTextRenderer(output)
        callbacks = ui_adapters.RendererCallbacks(renderer)

        assert callbacks is not None

    @_pytest.mark.asyncio
    async def test_thinking_complete_shows_summary(self) -> None:
        """on_thinking_complete shows word count summary."""
        import io as _io

        import brynhild.ui.plain as plain

        output = _io.StringIO()
        renderer = plain.PlainTextRenderer(output)
        callbacks = ui_adapters.RendererCallbacks(renderer)

        await callbacks.on_thinking_complete("one two three four five")

        output_text = output.getvalue()
        assert "💭" in output_text
        assert "5 words" in output_text


class TestToolResultTruncation:
    """Tests for tool result truncation to prevent context overflow."""

    def test_format_tool_result_truncates_long_output(self) -> None:
        """Long tool output should be truncated with message."""
        import brynhild.core.types as core_types

        # Create a result with 100k characters
        long_output = "x" * 100_000
        result = tools_base.ToolResult(success=True, output=long_output, error=None)

        message = core_types.format_tool_result_message(
            "test-id",
            result,
            max_chars=1000,  # Force small limit for test
        )

        content = message["content"]
        assert len(content) < 1100  # Allow for truncation message
        assert "TRUNCATED" in content
        assert "1,000 characters" in content

    def test_format_tool_result_preserves_short_output(self) -> None:
        """Short tool output should not be truncated."""
        import brynhild.core.types as core_types

        short_output = "Hello, world!"
        result = tools_base.ToolResult(success=True, output=short_output, error=None)

        message = core_types.format_tool_result_message("test-id", result)

        assert message["content"] == short_output
        assert "TRUNCATED" not in message["content"]

    def test_format_tool_result_uses_default_limit(self) -> None:
        """Default truncation limit should be DEFAULT_TOOL_RESULT_MAX_CHARS."""
        import brynhild.constants as constants
        import brynhild.core.types as core_types

        # Create output just under the limit - should not truncate
        under_limit = "x" * (constants.DEFAULT_TOOL_RESULT_MAX_CHARS - 100)
        result = tools_base.ToolResult(success=True, output=under_limit, error=None)

        message = core_types.format_tool_result_message("test-id", result)
        assert "TRUNCATED" not in message["content"]

        # Create output over the limit - should truncate
        over_limit = "x" * (constants.DEFAULT_TOOL_RESULT_MAX_CHARS + 1000)
        result = tools_base.ToolResult(success=True, output=over_limit, error=None)

        message = core_types.format_tool_result_message("test-id", result)
        assert "TRUNCATED" in message["content"]


# =============================================================================
# Finish Tool Integration Tests
# =============================================================================


class FinishToolMockProvider(api_base.LLMProvider):
    """Mock provider that returns Finish tool calls."""

    def __init__(
        self,
        responses: list[dict[str, _typing.Any]],
    ) -> None:
        self._responses = responses
        self._call_index = 0

    @property
    def name(self) -> str:
        return "finish-mock"

    @property
    def model(self) -> str:
        return "finish-mock-model"

    def supports_tools(self) -> bool:
        return True

    def supports_reasoning(self) -> bool:
        return False

    async def complete(
        self,
        messages: list[dict[str, _typing.Any]],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        tools: list[api_types.Tool] | None = None,
    ) -> api_types.CompletionResponse:
        text_parts = []
        tool_uses = []
        usage = None

        async for event in self.stream(
            messages, system=system, max_tokens=max_tokens, tools=tools
        ):
            if event.type == "text_delta" and event.text:
                text_parts.append(event.text)
            elif event.type == "tool_use_start" and event.tool_use:
                tool_uses.append(event.tool_use)
            elif event.type == "message_delta" and event.usage:
                usage = event.usage

        return api_types.CompletionResponse(
            id=f"call-{self._call_index}",
            content="".join(text_parts),
            stop_reason="tool_use" if tool_uses else "stop",
            usage=usage or api_types.Usage(input_tokens=100, output_tokens=50),
            tool_uses=tool_uses if tool_uses else None,
        )

    async def stream(
        self,
        messages: list[dict[str, _typing.Any]],  # noqa: ARG002
        *,
        system: str | None = None,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
        tools: list[api_types.Tool] | None = None,  # noqa: ARG002
    ) -> _typing.AsyncIterator[api_types.StreamEvent]:
        if self._call_index < len(self._responses):
            resp = self._responses[self._call_index]
        else:
            resp = {"text": "Default response"}

        if resp.get("text"):
            yield api_types.StreamEvent(type="text_delta", text=resp["text"])

        if resp.get("finish"):
            yield api_types.StreamEvent(
                type="tool_use_start",
                tool_use=api_types.ToolUse(
                    id=f"finish-{self._call_index}",
                    name="Finish",
                    input=resp["finish"],
                ),
            )
            stop_reason = "tool_use"
        else:
            stop_reason = "stop"

        yield api_types.StreamEvent(
            type="message_delta",
            stop_reason=stop_reason,
            usage=api_types.Usage(input_tokens=100, output_tokens=50),
        )

        self._call_index += 1


class TestFinishToolIntegration:
    """Tests for Finish tool handling in ConversationProcessor."""

    @_pytest.mark.asyncio
    async def test_finish_tool_sets_result(self) -> None:
        """
        When model calls Finish tool, ConversationResult includes finish_result.
        """
        provider = FinishToolMockProvider(responses=[
            {
                "text": "All done!",
                "finish": {"status": "success", "summary": "Task completed successfully"},
            },
        ])

        callbacks = MockCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "do something"}],
            system_prompt="You are helpful.",
        )

        assert result.finish_result is not None
        assert result.finish_result.status == "success"
        assert result.finish_result.summary == "Task completed successfully"

    @_pytest.mark.asyncio
    async def test_finish_tool_stops_processing(self) -> None:
        """
        Finish tool should end the processing loop.
        """
        provider = FinishToolMockProvider(responses=[
            {
                "text": "Done",
                "finish": {"status": "success", "summary": "Done"},
            },
            # This response should NOT be reached
            {
                "text": "This should not happen",
            },
        ])

        callbacks = MockCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "do something"}],
            system_prompt="You are helpful.",
        )

        assert result.stop_reason == "finish"
        assert result.finish_result is not None
        # Only one call should have been made
        assert provider._call_index == 1

    @_pytest.mark.asyncio
    async def test_finish_tool_with_next_steps(self) -> None:
        """
        Finish tool can include next_steps field.
        """
        provider = FinishToolMockProvider(responses=[
            {
                "finish": {
                    "status": "partial",
                    "summary": "Did some work",
                    "next_steps": "Please review and continue",
                },
            },
        ])

        callbacks = MockCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "do something"}],
            system_prompt="You are helpful.",
        )

        assert result.finish_result is not None
        assert result.finish_result.status == "partial"
        assert result.finish_result.next_steps == "Please review and continue"

    @_pytest.mark.asyncio
    async def test_require_finish_without_finish_injects_reminder(self) -> None:
        """
        With require_finish=True, text-only response triggers reminder.
        """
        provider = FinishToolMockProvider(responses=[
            # First response: text only (should trigger reminder)
            {"text": "Here's the answer"},
            # Second response: with Finish
            {"finish": {"status": "success", "summary": "Done"}},
        ])

        callbacks = MockCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            require_finish=True,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "do something"}],
            system_prompt="You are helpful.",
        )

        # Should eventually finish
        assert result.finish_result is not None
        # More than one call should have been made due to reminder
        assert provider._call_index > 1


# =============================================================================
# Thinking-Only Recovery Tests
# =============================================================================


class ThinkingOnlyMockProvider(api_base.LLMProvider):
    """Mock provider that returns only thinking content."""

    def __init__(
        self,
        responses: list[dict[str, _typing.Any]],
    ) -> None:
        self._responses = responses
        self._call_index = 0
        self.received_messages: list[list[dict[str, _typing.Any]]] = []

    @property
    def name(self) -> str:
        return "thinking-mock"

    @property
    def model(self) -> str:
        return "thinking-mock-model"

    def supports_tools(self) -> bool:
        return True

    def supports_reasoning(self) -> bool:
        return True

    async def complete(
        self,
        messages: list[dict[str, _typing.Any]],
        *,
        system: str | None = None,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
        tools: list[api_types.Tool] | None = None,  # noqa: ARG002
    ) -> api_types.CompletionResponse:
        self.received_messages.append(list(messages))
        if self._call_index < len(self._responses):
            resp = self._responses[self._call_index]
        else:
            resp = {"text": "Default response"}

        self._call_index += 1

        return api_types.CompletionResponse(
            id=f"call-{self._call_index}",
            content=resp.get("text", ""),
            thinking=resp.get("thinking"),
            stop_reason="stop",
            usage=api_types.Usage(input_tokens=100, output_tokens=50),
        )

    async def stream(
        self,
        messages: list[dict[str, _typing.Any]],
        *,
        system: str | None = None,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
        tools: list[api_types.Tool] | None = None,  # noqa: ARG002
    ) -> _typing.AsyncIterator[api_types.StreamEvent]:
        self.received_messages.append(list(messages))
        if self._call_index < len(self._responses):
            resp = self._responses[self._call_index]
        else:
            resp = {"text": "Default response"}

        if resp.get("thinking"):
            yield api_types.StreamEvent(
                type="thinking_delta",
                thinking=resp["thinking"],
            )

        if resp.get("text"):
            yield api_types.StreamEvent(type="text_delta", text=resp["text"])

        yield api_types.StreamEvent(
            type="message_delta",
            stop_reason="stop",
            usage=api_types.Usage(input_tokens=100, output_tokens=50),
        )

        self._call_index += 1


class TestThinkingOnlyRecovery:
    """Tests for handling models that produce only thinking."""

    @_pytest.mark.asyncio
    async def test_thinking_only_retries(self) -> None:
        """
        When model produces only thinking, processor should retry.
        """
        provider = ThinkingOnlyMockProvider(responses=[
            # First response: thinking only
            {"thinking": "Let me think about this..."},
            # Second response: thinking only
            {"thinking": "Still thinking..."},
            # Third response: actual text
            {"text": "Here's the answer", "thinking": "Figured it out"},
        ])

        callbacks = MockCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "hello"}],
            system_prompt="You are helpful.",
        )

        # Should eventually get a response
        assert result.response_text == "Here's the answer"
        # Multiple calls should have been made
        assert provider._call_index > 1

    @_pytest.mark.asyncio
    async def test_thinking_only_max_retries(self) -> None:
        """
        After max retries, conversation ends even with thinking only.
        """
        # Provider that always returns only thinking
        provider = ThinkingOnlyMockProvider(responses=[
            {"thinking": "Thinking 1..."},
            {"thinking": "Thinking 2..."},
            {"thinking": "Thinking 3..."},
            {"thinking": "Thinking 4..."},
            {"thinking": "Thinking 5..."},
        ])

        callbacks = MockCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "hello"}],
            system_prompt="You are helpful.",
        )

        # Should eventually give up (max 3 retries + 1 initial = 4 calls max)
        assert provider._call_index <= 4

    @_pytest.mark.asyncio
    async def test_normal_response_works(self) -> None:
        """
        Normal text response (with or without thinking) works fine.
        """
        provider = ThinkingOnlyMockProvider(responses=[
            {"text": "Hello!", "thinking": "I should be friendly"},
        ])

        callbacks = MockCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "hello"}],
            system_prompt="You are helpful.",
        )

        assert result.response_text == "Hello!"
        # Only one call needed
        assert provider._call_index == 1

    @_pytest.mark.asyncio
    async def test_thinking_only_preserves_reasoning_in_retry(self) -> None:
        """
        When model produces thinking-only, the retry should include the thinking
        as reasoning so the model has context.

        This is a critical test - without preserving reasoning, the model loses
        context about what it was trying to do, leading to repeated failures.
        """
        thinking_content = "I should call the Finish tool with success status."
        provider = ThinkingOnlyMockProvider(responses=[
            # First response: thinking only
            {"thinking": thinking_content},
            # Second response: actual text
            {"text": "Done!", "thinking": "Now I'll respond"},
        ])

        callbacks = MockCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "hello"}],
            system_prompt="You are helpful.",
        )

        # Should eventually get a response
        assert result.response_text == "Done!"
        # Two calls should have been made
        assert len(provider.received_messages) == 2

        # The second call should include the thinking from the first attempt
        # in the assistant message's reasoning field
        second_call_messages = provider.received_messages[1]

        # Find the assistant message with the thinking-only fake tool call
        thinking_only_assistant_msg = None
        for msg in second_call_messages:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                tool_calls = msg["tool_calls"]
                if any(tc.get("function", {}).get("name") == "incomplete_response"
                       for tc in tool_calls):
                    thinking_only_assistant_msg = msg
                    break

        assert thinking_only_assistant_msg is not None, (
            "Expected to find assistant message with incomplete_response tool call"
        )
        assert thinking_only_assistant_msg.get("reasoning") == thinking_content, (
            f"Expected reasoning field to contain '{thinking_content}', "
            f"got: {thinking_only_assistant_msg.get('reasoning')}"
        )


# =============================================================================
# Multi-round Tool Mock Provider
# =============================================================================


class ToolLoopMockProvider(api_base.LLMProvider):
    """
    Mock provider that requests tools for N rounds then completes.

    Used to test max_tool_rounds enforcement.
    """

    def __init__(
        self,
        tool_rounds: int = 10,
        tool_name: str = "MockTool",
    ) -> None:
        self._tool_rounds = tool_rounds
        self._tool_name = tool_name
        self._call_index = 0

    @property
    def name(self) -> str:
        return "tool-loop-mock"

    @property
    def model(self) -> str:
        return "tool-loop-model"

    def supports_tools(self) -> bool:
        return True

    def supports_reasoning(self) -> bool:
        return False

    async def complete(
        self,
        messages: list[dict[str, _typing.Any]],  # noqa: ARG002
        *,
        system: str | None = None,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
        tools: list[api_types.Tool] | None = None,  # noqa: ARG002
    ) -> api_types.CompletionResponse:
        self._call_index += 1

        # Request tool for first N rounds
        if self._call_index <= self._tool_rounds:
            return api_types.CompletionResponse(
                id=f"call-{self._call_index}",
                content="",
                stop_reason="tool_calls",
                usage=api_types.Usage(
                    input_tokens=100 * self._call_index,
                    output_tokens=20,
                ),
                tool_uses=[
                    api_types.ToolUse(
                        id=f"tool-{self._call_index}",
                        name=self._tool_name,
                        input={"round": self._call_index},
                    )
                ],
            )
        else:
            # Final response
            return api_types.CompletionResponse(
                id=f"call-{self._call_index}",
                content=f"Done after {self._call_index - 1} tool calls",
                stop_reason="stop",
                usage=api_types.Usage(
                    input_tokens=100 * self._call_index,
                    output_tokens=30,
                ),
            )

    async def stream(
        self,
        messages: list[dict[str, _typing.Any]],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        tools: list[api_types.Tool] | None = None,
    ) -> _typing.AsyncIterator[api_types.StreamEvent]:
        # Delegate to complete for simplicity
        response = await self.complete(
            messages, system=system, max_tokens=max_tokens, tools=tools
        )
        if response.tool_uses:
            for tu in response.tool_uses:
                yield api_types.StreamEvent(type="tool_use_start", tool_use=tu)
        else:
            yield api_types.StreamEvent(type="text_delta", text=response.content)
        yield api_types.StreamEvent(
            type="message_delta",
            stop_reason=response.stop_reason,
            usage=response.usage,
        )


class CancellableMockCallbacks(conversation.ConversationCallbacks):
    """
    Mock callbacks that can be cancelled mid-conversation.
    """

    def __init__(self, cancel_after_rounds: int = 1) -> None:
        self._cancel_after_rounds = cancel_after_rounds
        self._current_round = 0
        self._cancelled = False
        self.rounds_seen: list[int] = []
        self.tool_calls_seen: list[str] = []

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

    async def on_text_complete(
        self, full_text: str, thinking: str | None  # noqa: ARG002
    ) -> None:
        pass

    async def on_tool_call(
        self, tool_call: _typing.Any
    ) -> None:
        self.tool_calls_seen.append(tool_call.tool_name)

    async def request_tool_permission(
        self, tool_call: _typing.Any  # noqa: ARG002
    ) -> bool:
        return True

    async def on_tool_result(self, result: _typing.Any) -> None:  # noqa: ARG002
        pass

    async def on_round_start(self, round_num: int) -> None:
        self._current_round = round_num
        self.rounds_seen.append(round_num)
        # Cancel after specified number of rounds
        if round_num > self._cancel_after_rounds:
            self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    async def on_info(self, message: str) -> None:  # noqa: ARG002
        pass

    async def on_usage_update(
        self,
        input_tokens: int,  # noqa: ARG002
        output_tokens: int,  # noqa: ARG002
        usage: _typing.Any = None,  # noqa: ARG002
    ) -> None:
        pass


class PermissionDenyingCallbacks(conversation.ConversationCallbacks):
    """
    Mock callbacks that deny tool permissions.
    """

    def __init__(self, deny_tools: set[str] | None = None) -> None:
        self._deny_tools = deny_tools or set()
        self.permission_requests: list[str] = []
        self.tool_results: list[tuple[str, bool]] = []
        self.tool_calls_seen: list[str] = []

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

    async def on_text_complete(
        self, full_text: str, thinking: str | None  # noqa: ARG002
    ) -> None:
        pass

    async def on_tool_call(self, tool_call: _typing.Any) -> None:
        self.tool_calls_seen.append(tool_call.tool_name)

    async def request_tool_permission(
        self, tool_call: _typing.Any
    ) -> bool:
        self.permission_requests.append(tool_call.tool_name)
        # Deny if tool name is in deny set
        return tool_call.tool_name not in self._deny_tools

    async def on_tool_result(self, result: _typing.Any) -> None:
        self.tool_results.append((result.tool_name, result.result.success))

    async def on_round_start(self, round_num: int) -> None:  # noqa: ARG002
        pass

    def is_cancelled(self) -> bool:
        return False

    async def on_info(self, message: str) -> None:  # noqa: ARG002
        pass

    async def on_usage_update(
        self,
        input_tokens: int,  # noqa: ARG002
        output_tokens: int,  # noqa: ARG002
        usage: _typing.Any = None,  # noqa: ARG002
    ) -> None:
        pass


# =============================================================================
# Max Tool Rounds Tests
# =============================================================================


class TestMaxToolRounds:
    """Tests for max_tool_rounds enforcement."""

    @_pytest.mark.asyncio
    async def test_max_rounds_stops_loop(self) -> None:
        """
        After max_tool_rounds, tool loop ends even if model wants more.

        This is critical for preventing runaway tool loops from
        consuming infinite resources.
        """
        # Provider wants 10 tool rounds
        provider = ToolLoopMockProvider(tool_rounds=10, tool_name="MockTool")

        # But we limit to 2
        max_rounds = 2

        # Set up tool registry
        registry = tools_registry.ToolRegistry()
        registry.register(MockTool(name="MockTool"))

        callbacks = MockCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            max_tool_rounds=max_rounds,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "Use tools please"}],
            system_prompt="You are helpful.",
        )

        # Should have stopped after max_rounds
        # The provider's call_index shows how many API calls were made
        # With max_tool_rounds=2, we get: round 1 (tool), round 2 (tool), then exit
        # So we should see exactly 2 rounds, not 10
        assert provider._call_index == max_rounds, (
            f"Expected {max_rounds} rounds, got {provider._call_index}"
        )

        # Result should indicate we hit the limit (not a normal stop)
        # The response text will be empty because we never got to the final response
        assert result.response_text == ""

    @_pytest.mark.asyncio
    async def test_completes_if_under_max_rounds(self) -> None:
        """
        If model finishes before max_rounds, conversation completes normally.
        """
        # Provider only needs 2 tool rounds
        provider = ToolLoopMockProvider(tool_rounds=2, tool_name="MockTool")

        # Set limit higher
        max_rounds = 10

        registry = tools_registry.ToolRegistry()
        registry.register(MockTool(name="MockTool"))

        callbacks = MockCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            max_tool_rounds=max_rounds,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "Use tools please"}],
            system_prompt="You are helpful.",
        )

        # Should complete with final response after 2 tool calls + 1 final
        assert provider._call_index == 3  # 2 tool calls + 1 final response
        assert "Done after" in result.response_text


# =============================================================================
# Cancellation Tests
# =============================================================================


class TestCancellation:
    """Tests for cancellation during conversation."""

    @_pytest.mark.asyncio
    async def test_cancellation_stops_tool_loop(self) -> None:
        """
        is_cancelled() returning True stops the tool loop.
        """
        # Provider wants 10 rounds
        provider = ToolLoopMockProvider(tool_rounds=10, tool_name="MockTool")

        registry = tools_registry.ToolRegistry()
        registry.register(MockTool(name="MockTool"))

        # Cancel after 2 rounds
        callbacks = CancellableMockCallbacks(cancel_after_rounds=2)

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            max_tool_rounds=100,  # High limit
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "Use tools"}],
            system_prompt="You are helpful.",
        )

        # Should have cancelled flag set
        assert result.cancelled is True
        # Should have stopped after 2 rounds (round 3 triggers cancellation check)
        assert len(callbacks.rounds_seen) <= 3
        # Stop reason should indicate cancellation
        assert result.stop_reason == "cancelled"

    @_pytest.mark.asyncio
    async def test_cancellation_preserves_partial_response(self) -> None:
        """
        Cancelled conversation should preserve any partial response.
        """
        # Provider that returns text first, then tools
        provider = MockProvider(
            responses=[
                api_types.CompletionResponse(
                    id="resp-1",
                    content="Starting to work on this...",
                    stop_reason="tool_calls",
                    usage=api_types.Usage(input_tokens=100, output_tokens=50),
                    tool_uses=[
                        api_types.ToolUse(
                            id="tool-1",
                            name="MockTool",
                            input={},
                        )
                    ],
                ),
            ]
        )

        registry = tools_registry.ToolRegistry()
        registry.register(MockTool(name="MockTool"))

        # Cancel immediately on first round
        callbacks = CancellableMockCallbacks(cancel_after_rounds=0)

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "hello"}],
            system_prompt="You are helpful.",
        )

        assert result.cancelled is True


# =============================================================================
# Dry Run Tests
# =============================================================================


class TestDryRun:
    """Tests for dry_run mode."""

    @_pytest.mark.asyncio
    async def test_dry_run_shows_tool_call_but_doesnt_execute(self) -> None:
        """
        In dry_run, tool calls are shown but not actually executed.

        This is useful for previewing what the model wants to do
        without side effects.
        """
        provider = MockProvider(
            stream_events=[
                # First call: model requests tool
                [
                    api_types.StreamEvent(
                        type="tool_use_start",
                        tool_use=api_types.ToolUse(
                            id="tool-1",
                            name="MockTool",
                            input={"action": "do_something"},
                        ),
                    ),
                    api_types.StreamEvent(
                        type="message_delta",
                        stop_reason="tool_calls",
                        usage=api_types.Usage(input_tokens=100, output_tokens=20),
                    ),
                ],
                # Second call: model responds after tool "ran"
                [
                    api_types.StreamEvent(
                        type="text_delta",
                        text="Done with dry run",
                    ),
                    api_types.StreamEvent(
                        type="message_delta",
                        stop_reason="stop",
                        usage=api_types.Usage(input_tokens=200, output_tokens=30),
                    ),
                ],
            ]
        )

        registry = tools_registry.ToolRegistry()
        tool = MockTool(name="MockTool")
        registry.register(tool)

        callbacks = MockCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            dry_run=True,  # KEY: dry run enabled
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "Do something"}],
            system_prompt="You are helpful.",
        )

        # Extract tool call events from callbacks
        tool_call_events = [e for e in callbacks.events if e[0] == "tool_call"]
        tool_result_events = [e for e in callbacks.events if e[0] == "tool_result"]

        # Tool call should have been displayed
        assert len(tool_call_events) == 1
        assert tool_call_events[0][1].tool_name == "MockTool"

        # Tool result should show dry run message
        assert len(tool_result_events) == 1
        assert "dry run" in tool_result_events[0][1].result.output.lower()

        # Final response should be present
        assert result.response_text == "Done with dry run"


# =============================================================================
# Permission Tests
# =============================================================================


class TestPermissionDenied:
    """Tests for permission handling."""

    @_pytest.mark.asyncio
    async def test_permission_denied_returns_error_to_model(self) -> None:
        """
        If user denies permission, tool returns error result to model.

        The model should receive feedback that the tool wasn't run.
        """
        # Use stream_events format which MockProvider.stream() understands
        provider = MockProvider(
            stream_events=[
                # First call: model requests tool
                [
                    api_types.StreamEvent(
                        type="tool_use_start",
                        tool_use=api_types.ToolUse(
                            id="tool-1",
                            name="DangerousTool",
                            input={},
                        ),
                    ),
                    api_types.StreamEvent(
                        type="message_delta",
                        stop_reason="tool_calls",
                        usage=api_types.Usage(input_tokens=100, output_tokens=20),
                    ),
                ],
                # Second call: model responds to denial
                [
                    api_types.StreamEvent(
                        type="text_delta",
                        text="I understand, I won't do that.",
                    ),
                    api_types.StreamEvent(
                        type="message_delta",
                        stop_reason="stop",
                        usage=api_types.Usage(input_tokens=200, output_tokens=30),
                    ),
                ],
            ]
        )

        # Tool that requires permission
        registry = tools_registry.ToolRegistry()
        registry.register(MockTool(name="DangerousTool", requires_permission=True))

        # Callbacks that deny this tool
        callbacks = PermissionDenyingCallbacks(deny_tools={"DangerousTool"})

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=False,  # Must ask for permission
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "Do dangerous thing"}],
            system_prompt="You are helpful.",
        )

        # Permission should have been requested
        assert "DangerousTool" in callbacks.permission_requests

        # Tool result should show failure (permission denied)
        assert len(callbacks.tool_results) == 1
        assert callbacks.tool_results[0][1] is False  # success=False

        # Model should have responded to the denial
        assert "won't" in result.response_text.lower()

    @_pytest.mark.asyncio
    async def test_auto_approve_skips_permission_dialog(self) -> None:
        """
        With auto_approve_tools=True, permission dialog is not shown.
        """
        provider = MockProvider(
            stream_events=[
                # First call: model requests tool
                [
                    api_types.StreamEvent(
                        type="tool_use_start",
                        tool_use=api_types.ToolUse(
                            id="tool-1",
                            name="DangerousTool",
                            input={},
                        ),
                    ),
                    api_types.StreamEvent(
                        type="message_delta",
                        stop_reason="tool_calls",
                        usage=api_types.Usage(input_tokens=100, output_tokens=20),
                    ),
                ],
                # Second call: model responds after tool executes
                [
                    api_types.StreamEvent(type="text_delta", text="Done!"),
                    api_types.StreamEvent(
                        type="message_delta",
                        stop_reason="stop",
                        usage=api_types.Usage(input_tokens=200, output_tokens=10),
                    ),
                ],
            ]
        )

        registry = tools_registry.ToolRegistry()
        registry.register(MockTool(name="DangerousTool", requires_permission=True))

        # These callbacks would deny, but auto_approve should bypass them
        callbacks = PermissionDenyingCallbacks(deny_tools={"DangerousTool"})

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,  # KEY: auto approve
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "Do dangerous thing"}],
            system_prompt="You are helpful.",
        )

        # Permission should NOT have been requested (auto-approved)
        assert "DangerousTool" not in callbacks.permission_requests

        # Tool should have succeeded
        assert len(callbacks.tool_results) == 1
        assert callbacks.tool_results[0][1] is True  # success=True

        assert result.response_text == "Done!"

    @_pytest.mark.asyncio
    async def test_tool_without_requires_permission_executes_without_asking(
        self,
    ) -> None:
        """
        Tools with requires_permission=False run without asking.
        """
        provider = MockProvider(
            stream_events=[
                # First call: model requests tool
                [
                    api_types.StreamEvent(
                        type="tool_use_start",
                        tool_use=api_types.ToolUse(
                            id="tool-1",
                            name="SafeTool",
                            input={},
                        ),
                    ),
                    api_types.StreamEvent(
                        type="message_delta",
                        stop_reason="tool_calls",
                        usage=api_types.Usage(input_tokens=100, output_tokens=20),
                    ),
                ],
                # Second call: model responds
                [
                    api_types.StreamEvent(type="text_delta", text="Done!"),
                    api_types.StreamEvent(
                        type="message_delta",
                        stop_reason="stop",
                        usage=api_types.Usage(input_tokens=200, output_tokens=10),
                    ),
                ],
            ]
        )

        registry = tools_registry.ToolRegistry()
        # Tool does NOT require permission
        registry.register(MockTool(name="SafeTool", requires_permission=False))

        # These callbacks would deny if asked, but tool doesn't require permission
        callbacks = PermissionDenyingCallbacks(deny_tools={"SafeTool"})

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=False,  # Must ask for permission... but tool doesn't need it
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "Do safe thing"}],
            system_prompt="You are helpful.",
        )

        # Permission should NOT have been requested (tool doesn't need it)
        assert len(callbacks.permission_requests) == 0

        # Tool should have executed successfully
        assert len(callbacks.tool_results) == 1
        assert callbacks.tool_results[0][1] is True

        assert result.response_text == "Done!"

