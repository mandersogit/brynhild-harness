"""
Tests for UI callback adapters.

These adapters bridge core conversation callbacks with renderer implementations.
"""

import typing as _typing

import pytest as _pytest

import brynhild.core.types as core_types
import brynhild.tools.base as tools_base
import brynhild.ui.adapters as adapters


class MockRenderer:
    """Mock renderer that records all method calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, _typing.Any]] = []
        self._streaming = False
        self._thinking_stream_active = False

    def start_streaming(self) -> None:
        self.calls.append(("start_streaming", None))
        self._streaming = True

    def end_streaming(self) -> None:
        self.calls.append(("end_streaming", None))
        self._streaming = False

    def show_assistant_text(self, text: str, streaming: bool = False) -> None:
        self.calls.append(("show_assistant_text", {"text": text, "streaming": streaming}))

    def show_info(self, message: str) -> None:
        self.calls.append(("show_info", message))

    def show_tool_call(self, tool_call: core_types.ToolCallDisplay) -> None:
        self.calls.append(("show_tool_call", tool_call))

    def show_tool_result(self, result: core_types.ToolResultDisplay) -> None:
        self.calls.append(("show_tool_result", result))

    def finalize(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        self.calls.append(("finalize", {"input": input_tokens, "output": output_tokens}))

    # Thinking streaming methods
    def start_thinking_stream(self) -> None:
        self.calls.append(("start_thinking_stream", None))
        self._thinking_stream_active = True

    def update_thinking_stream(self, text: str) -> None:
        self.calls.append(("update_thinking_stream", text))

    def end_thinking_stream(self, persist: bool = False) -> None:
        self.calls.append(("end_thinking_stream", {"persist": persist}))
        self._thinking_stream_active = False

    def show_thinking(self, text: str) -> None:
        self.calls.append(("show_thinking", text))

    def update_token_counts(self, input_tokens: int, output_tokens: int) -> None:
        self.calls.append(("update_token_counts", {"input": input_tokens, "output": output_tokens}))

    def prompt_permission(
        self,
        tool_call: core_types.ToolCallDisplay,
        auto_approve: bool = False,  # noqa: ARG002
    ) -> bool:
        self.calls.append(("prompt_permission", tool_call))
        # Default to denying permission in tests
        return False


class TestRendererCallbacks:
    """Tests for RendererCallbacks adapter."""

    @_pytest.mark.asyncio
    async def test_stream_lifecycle(self) -> None:
        """on_stream_start/end call renderer methods."""
        renderer = MockRenderer()
        callbacks = adapters.RendererCallbacks(renderer)

        await callbacks.on_stream_start()
        await callbacks.on_stream_end()

        assert ("start_streaming", None) in renderer.calls
        assert ("end_streaming", None) in renderer.calls

    @_pytest.mark.asyncio
    async def test_text_delta_shown(self) -> None:
        """Text deltas are shown through renderer."""
        renderer = MockRenderer()
        callbacks = adapters.RendererCallbacks(renderer)

        await callbacks.on_text_delta("Hello")

        # Find the text call
        text_calls = [c for c in renderer.calls if c[0] == "show_assistant_text"]
        assert len(text_calls) == 1
        assert text_calls[0][1]["text"] == "Hello"

    @_pytest.mark.asyncio
    async def test_leading_whitespace_skipped(self) -> None:
        """Leading whitespace-only content is skipped."""
        renderer = MockRenderer()
        callbacks = adapters.RendererCallbacks(renderer)

        # Start of stream - whitespace should be skipped
        await callbacks.on_text_delta("\n\n")
        await callbacks.on_text_delta("  ")
        await callbacks.on_text_delta("Hello")

        # Only "Hello" should be shown
        text_calls = [c for c in renderer.calls if c[0] == "show_assistant_text"]
        assert len(text_calls) == 1
        assert text_calls[0][1]["text"] == "Hello"

    @_pytest.mark.asyncio
    async def test_whitespace_after_content_shown(self) -> None:
        """Whitespace after content starts is not skipped."""
        renderer = MockRenderer()
        callbacks = adapters.RendererCallbacks(renderer)

        await callbacks.on_text_delta("Hello")
        await callbacks.on_text_delta(" ")
        await callbacks.on_text_delta("World")

        text_calls = [c for c in renderer.calls if c[0] == "show_assistant_text"]
        assert len(text_calls) == 3


class TestThinkingStreamHandling:
    """Tests for thinking stream handling."""

    @_pytest.mark.asyncio
    async def test_thinking_delta_starts_stream(self) -> None:
        """First thinking delta starts the thinking stream."""
        renderer = MockRenderer()
        callbacks = adapters.RendererCallbacks(renderer)

        await callbacks.on_thinking_delta("Let me think...")

        assert ("start_thinking_stream", None) in renderer.calls
        assert ("update_thinking_stream", "Let me think...") in renderer.calls

    @_pytest.mark.asyncio
    async def test_thinking_delta_updates_stream(self) -> None:
        """Subsequent deltas update the stream."""
        renderer = MockRenderer()
        callbacks = adapters.RendererCallbacks(renderer)

        await callbacks.on_thinking_delta("Part 1")
        await callbacks.on_thinking_delta("Part 2")

        updates = [c for c in renderer.calls if c[0] == "update_thinking_stream"]
        assert len(updates) == 2
        # Stream should only start once
        starts = [c for c in renderer.calls if c[0] == "start_thinking_stream"]
        assert len(starts) == 1

    @_pytest.mark.asyncio
    async def test_thinking_complete_ends_stream(self) -> None:
        """on_thinking_complete ends the stream."""
        renderer = MockRenderer()
        callbacks = adapters.RendererCallbacks(renderer)

        await callbacks.on_thinking_delta("Thinking...")
        await callbacks.on_thinking_complete("Full thinking text")

        assert ("end_thinking_stream", {"persist": False}) in renderer.calls

    @_pytest.mark.asyncio
    async def test_show_thinking_persists_panel(self) -> None:
        """With show_thinking=True, panel persists."""
        renderer = MockRenderer()
        callbacks = adapters.RendererCallbacks(renderer, show_thinking=True)

        await callbacks.on_thinking_delta("Thinking...")
        await callbacks.on_thinking_complete("Full thinking text")

        # persist=True when show_thinking is enabled
        assert ("end_thinking_stream", {"persist": True}) in renderer.calls

    @_pytest.mark.asyncio
    async def test_thinking_summary_when_not_showing(self) -> None:
        """Without show_thinking, shows word count summary."""
        renderer = MockRenderer()
        callbacks = adapters.RendererCallbacks(renderer, show_thinking=False)

        await callbacks.on_thinking_delta("Some thinking here")
        await callbacks.on_thinking_complete("Some thinking here")

        # Should show summary
        info_calls = [c for c in renderer.calls if c[0] == "show_info"]
        assert len(info_calls) >= 1
        assert "Thinking:" in info_calls[-1][1]


class TestTokenUpdates:
    """Tests for token count handling."""

    @_pytest.mark.asyncio
    async def test_usage_update_calls_renderer(self) -> None:
        """on_usage_update calls renderer.update_token_counts."""
        renderer = MockRenderer()
        callbacks = adapters.RendererCallbacks(renderer)

        await callbacks.on_usage_update(1000, 200)

        assert ("update_token_counts", {"input": 1000, "output": 200}) in renderer.calls

    @_pytest.mark.asyncio
    async def test_multiple_usage_updates(self) -> None:
        """Multiple usage updates are all forwarded."""
        renderer = MockRenderer()
        callbacks = adapters.RendererCallbacks(renderer)

        await callbacks.on_usage_update(1000, 50)
        await callbacks.on_usage_update(2000, 100)
        await callbacks.on_usage_update(3000, 150)

        updates = [c for c in renderer.calls if c[0] == "update_token_counts"]
        assert len(updates) == 3


class TestToolCallHandling:
    """Tests for tool call display."""

    @_pytest.mark.asyncio
    async def test_tool_call_displayed(self) -> None:
        """Tool calls are passed to renderer."""
        renderer = MockRenderer()
        callbacks = adapters.RendererCallbacks(renderer)

        tool_call = core_types.ToolCallDisplay(
            tool_id="test-id",
            tool_name="TestTool",
            tool_input={"arg": "value"},
            is_recovered=False,
        )
        await callbacks.on_tool_call(tool_call)

        tc_calls = [c for c in renderer.calls if c[0] == "show_tool_call"]
        assert len(tc_calls) == 1
        assert tc_calls[0][1].tool_name == "TestTool"

    @_pytest.mark.asyncio
    async def test_tool_result_displayed(self) -> None:
        """Tool results are passed to renderer."""
        renderer = MockRenderer()
        callbacks = adapters.RendererCallbacks(renderer)

        result = core_types.ToolResultDisplay(
            tool_id="test-id",
            tool_name="TestTool",
            result=tools_base.ToolResult(success=True, output="output"),
        )
        await callbacks.on_tool_result(result)

        result_calls = [c for c in renderer.calls if c[0] == "show_tool_result"]
        assert len(result_calls) == 1
        assert result_calls[0][1].tool_name == "TestTool"


class TestAutoApprove:
    """Tests for auto-approve mode."""

    @_pytest.mark.asyncio
    async def test_auto_approve_returns_true(self) -> None:
        """With auto_approve=True, permission is automatically granted."""
        renderer = MockRenderer()
        callbacks = adapters.RendererCallbacks(renderer, auto_approve=True)

        tool_call = core_types.ToolCallDisplay(
            tool_id="test-id",
            tool_name="DangerousTool",
            tool_input={},
            is_recovered=False,
        )
        result = await callbacks.request_tool_permission(tool_call)

        assert result is True

    @_pytest.mark.asyncio
    async def test_without_auto_approve_returns_false(self) -> None:
        """Without auto_approve, permission defaults to False (renderer decides)."""
        renderer = MockRenderer()
        # Note: MockRenderer doesn't implement request_permission, so default is False
        callbacks = adapters.RendererCallbacks(renderer, auto_approve=False)

        tool_call = core_types.ToolCallDisplay(
            tool_id="test-id",
            tool_name="DangerousTool",
            tool_input={},
            is_recovered=False,
        )
        result = await callbacks.request_tool_permission(tool_call)

        # Without auto_approve and no renderer implementation, defaults to False
        assert result is False


class TestStateReset:
    """Tests for state tracking across calls."""

    @_pytest.mark.asyncio
    async def test_state_resets_on_stream_start(self) -> None:
        """State is reset when new stream starts."""
        renderer = MockRenderer()
        callbacks = adapters.RendererCallbacks(renderer)

        # Simulate first turn
        await callbacks.on_stream_start()
        await callbacks.on_thinking_delta("Think 1")
        await callbacks.on_text_delta("Response 1")
        await callbacks.on_stream_end()

        # Simulate second turn - state should reset
        await callbacks.on_stream_start()

        # Now whitespace should be skipped again (content_started is reset)
        await callbacks.on_text_delta("\n\n")  # Should be skipped
        await callbacks.on_text_delta("Response 2")

        # Count text calls - should have 2 (one from each turn's actual content)
        text_calls = [c for c in renderer.calls if c[0] == "show_assistant_text"]
        assert len(text_calls) == 2
        assert text_calls[0][1]["text"] == "Response 1"
        assert text_calls[1][1]["text"] == "Response 2"

