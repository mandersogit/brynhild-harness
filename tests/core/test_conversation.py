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

