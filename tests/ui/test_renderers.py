"""Tests for UI renderers."""

import io as _io
import json as _json

import pytest as _pytest

import brynhild.tools.base as tools_base
import brynhild.ui as ui


class TestToolCallDisplay:
    """Tests for ToolCallDisplay dataclass."""

    def test_create_tool_call_display(self) -> None:
        """Should create a tool call display with required fields."""
        display = ui.ToolCallDisplay(
            tool_name="Bash",
            tool_input={"command": "echo hello"},
        )
        assert display.tool_name == "Bash"
        assert display.tool_input == {"command": "echo hello"}
        assert display.tool_id is None

    def test_create_tool_call_display_with_id(self) -> None:
        """Should create a tool call display with optional id."""
        display = ui.ToolCallDisplay(
            tool_name="Read",
            tool_input={"file_path": "test.txt"},
            tool_id="call_123",
        )
        assert display.tool_id == "call_123"


class TestToolResultDisplay:
    """Tests for ToolResultDisplay dataclass."""

    def test_create_tool_result_display_success(self) -> None:
        """Should create a successful tool result display."""
        result = tools_base.ToolResult(
            success=True,
            output="hello\n",
            error=None,
        )
        display = ui.ToolResultDisplay(
            tool_name="Bash",
            result=result,
        )
        assert display.tool_name == "Bash"
        assert display.result.success is True
        assert display.result.output == "hello\n"

    def test_create_tool_result_display_error(self) -> None:
        """Should create a failed tool result display."""
        result = tools_base.ToolResult(
            success=False,
            output="",
            error="Command not found",
        )
        display = ui.ToolResultDisplay(
            tool_name="Bash",
            result=result,
            tool_id="call_456",
        )
        assert display.result.success is False
        assert display.result.error == "Command not found"


class TestPlainTextRenderer:
    """Tests for PlainTextRenderer."""

    def test_show_user_message(self) -> None:
        """Should output user message with prefix."""
        output = _io.StringIO()
        renderer = ui.PlainTextRenderer(output=output)
        renderer.show_user_message("Hello, world!")
        assert output.getvalue() == "User: Hello, world!\n"

    def test_show_assistant_text_complete(self) -> None:
        """Should output assistant text with prefix."""
        output = _io.StringIO()
        renderer = ui.PlainTextRenderer(output=output)
        renderer.show_assistant_text("Hi there!")
        assert output.getvalue() == "Assistant: Hi there!\n"

    def test_show_assistant_text_streaming(self) -> None:
        """Should output streaming text without newline."""
        output = _io.StringIO()
        renderer = ui.PlainTextRenderer(output=output)
        renderer.start_streaming()
        renderer.show_assistant_text("Hello", streaming=True)
        renderer.show_assistant_text(" world", streaming=True)
        renderer.end_streaming()
        assert output.getvalue() == "Assistant: Hello world\n"

    def test_show_tool_call(self) -> None:
        """Should output tool call with parameters."""
        output = _io.StringIO()
        renderer = ui.PlainTextRenderer(output=output)
        tool_call = ui.ToolCallDisplay(
            tool_name="Bash",
            tool_input={"command": "echo test"},
        )
        renderer.show_tool_call(tool_call)
        result = output.getvalue()
        assert "Tool: Bash]" in result  # Icon prefix varies
        assert "command: echo test" in result

    def test_show_tool_result_success(self) -> None:
        """Should output successful tool result."""
        output = _io.StringIO()
        renderer = ui.PlainTextRenderer(output=output)
        result = tools_base.ToolResult(success=True, output="test output", error=None)
        display = ui.ToolResultDisplay(tool_name="Bash", result=result)
        renderer.show_tool_result(display)
        result_text = output.getvalue()
        assert "✓" in result_text  # Success icon present
        assert "Bash]" in result_text
        assert "test output" in result_text

    def test_show_tool_result_failure(self) -> None:
        """Should output failed tool result."""
        output = _io.StringIO()
        renderer = ui.PlainTextRenderer(output=output)
        result = tools_base.ToolResult(success=False, output="", error="Failed!")
        display = ui.ToolResultDisplay(tool_name="Bash", result=result)
        renderer.show_tool_result(display)
        result_text = output.getvalue()
        assert "✗" in result_text  # Failure icon present
        assert "Bash]" in result_text
        assert "Error: Failed!" in result_text

    def test_show_error(self) -> None:
        """Should output error to stderr."""
        error = _io.StringIO()
        renderer = ui.PlainTextRenderer(error=error)
        renderer.show_error("Something went wrong")
        assert error.getvalue() == "Error: Something went wrong\n"

    def test_show_info(self) -> None:
        """Should output info message."""
        output = _io.StringIO()
        renderer = ui.PlainTextRenderer(output=output)
        renderer.show_info("Processing...")
        assert output.getvalue() == "Processing...\n"

    def test_prompt_permission_auto_approve(self) -> None:
        """Should return True when auto_approve is True."""
        renderer = ui.PlainTextRenderer()
        tool_call = ui.ToolCallDisplay(
            tool_name="Bash",
            tool_input={"command": "rm -rf /"},
        )
        assert renderer.prompt_permission(tool_call, auto_approve=True) is True

    def test_prompt_permission_deny_by_default(self) -> None:
        """Should return False when not auto_approve (non-interactive)."""
        output = _io.StringIO()
        renderer = ui.PlainTextRenderer(output=output)
        tool_call = ui.ToolCallDisplay(
            tool_name="Bash",
            tool_input={"command": "rm -rf /"},
        )
        assert renderer.prompt_permission(tool_call, auto_approve=False) is False
        assert "Permission required" in output.getvalue()


class TestCaptureRenderer:
    """Tests for CaptureRenderer (testing helper)."""

    def test_captures_output(self) -> None:
        """Should capture all output for inspection."""
        renderer = ui.CaptureRenderer()
        renderer.show_user_message("Hello")
        renderer.show_assistant_text("Hi")
        renderer.show_info("Done")

        output = renderer.get_output()
        assert "User: Hello" in output
        assert "Assistant: Hi" in output
        assert "Done" in output

    def test_captures_error(self) -> None:
        """Should capture error output separately."""
        renderer = ui.CaptureRenderer()
        renderer.show_error("Bad things")

        assert renderer.get_error() == "Error: Bad things\n"
        assert "Bad things" not in renderer.get_output()

    def test_clear_resets_buffers(self) -> None:
        """Should clear captured content."""
        renderer = ui.CaptureRenderer()
        renderer.show_info("First message")
        assert "First message" in renderer.get_output()

        renderer.clear()
        assert renderer.get_output() == ""
        assert renderer.get_error() == ""


class TestJSONRenderer:
    """Tests for JSONRenderer."""

    def test_accumulates_messages(self) -> None:
        """Should accumulate messages for JSON output."""
        output = _io.StringIO()
        renderer = ui.JSONRenderer(output=output)

        renderer.show_user_message("Hello")
        renderer.show_assistant_text("Hi there!")
        renderer.finalize()

        result = _json.loads(output.getvalue())
        assert result["response"] == "Hi there!"
        assert result["messages"] == [{"role": "user", "content": "Hello"}]

    def test_accumulates_tool_calls(self) -> None:
        """Should accumulate tool calls."""
        output = _io.StringIO()
        renderer = ui.JSONRenderer(output=output)

        tool_call = ui.ToolCallDisplay(
            tool_name="Bash",
            tool_input={"command": "echo test"},
            tool_id="call_1",
        )
        renderer.show_tool_call(tool_call)
        renderer.finalize()

        result = _json.loads(output.getvalue())
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["tool"] == "Bash"
        assert result["tool_calls"][0]["id"] == "call_1"

    def test_accumulates_tool_results(self) -> None:
        """Should accumulate tool results."""
        output = _io.StringIO()
        renderer = ui.JSONRenderer(output=output)

        tool_result = tools_base.ToolResult(success=True, output="hello", error=None)
        display = ui.ToolResultDisplay(
            tool_name="Bash",
            result=tool_result,
            tool_id="call_1",
        )
        renderer.show_tool_result(display)
        renderer.finalize()

        result = _json.loads(output.getvalue())
        assert len(result["tool_results"]) == 1
        assert result["tool_results"][0]["success"] is True
        assert result["tool_results"][0]["output"] == "hello"

    def test_accumulates_errors(self) -> None:
        """Should include errors in output."""
        output = _io.StringIO()
        renderer = ui.JSONRenderer(output=output)

        renderer.show_error("Something failed")
        renderer.finalize()

        result = _json.loads(output.getvalue())
        assert result["error"] == "Something failed"

    def test_multiple_errors_as_list(self) -> None:
        """Should output multiple errors as a list."""
        output = _io.StringIO()
        renderer = ui.JSONRenderer(output=output)

        renderer.show_error("Error 1")
        renderer.show_error("Error 2")
        renderer.finalize()

        result = _json.loads(output.getvalue())
        assert result["errors"] == ["Error 1", "Error 2"]

    def test_finalize_includes_result_data(self) -> None:
        """Should include provided result data."""
        output = _io.StringIO()
        renderer = ui.JSONRenderer(output=output)

        renderer.show_assistant_text("Done")
        renderer.finalize(
            {
                "provider": "anthropic",
                "model": "claude-3",
                "usage": {"input_tokens": 10, "output_tokens": 20},
            }
        )

        result = _json.loads(output.getvalue())
        assert result["provider"] == "anthropic"
        assert result["model"] == "claude-3"
        assert result["usage"]["input_tokens"] == 10

    def test_reset_clears_state(self) -> None:
        """Should reset accumulated state."""
        output = _io.StringIO()
        renderer = ui.JSONRenderer(output=output)

        renderer.show_user_message("First")
        renderer.reset()
        renderer.show_user_message("Second")
        renderer.finalize()

        result = _json.loads(output.getvalue())
        assert result["messages"] == [{"role": "user", "content": "Second"}]

    def test_prompt_permission_auto_approve(self) -> None:
        """Should return auto_approve value."""
        renderer = ui.JSONRenderer()
        tool_call = ui.ToolCallDisplay(tool_name="Bash", tool_input={})
        assert renderer.prompt_permission(tool_call, auto_approve=True) is True
        assert renderer.prompt_permission(tool_call, auto_approve=False) is False


class TestRichConsoleRenderer:
    """Tests for RichConsoleRenderer.

    Note: These are basic smoke tests. Full Rich output testing
    would require capturing the console output.
    """

    def test_prompt_permission_auto_approve(self) -> None:
        """Should return True when auto_approve is True."""
        renderer = ui.RichConsoleRenderer()
        tool_call = ui.ToolCallDisplay(tool_name="Bash", tool_input={})
        assert renderer.prompt_permission(tool_call, auto_approve=True) is True

    def test_streaming_lifecycle_does_not_crash(self) -> None:
        """Verify streaming lifecycle completes without raising exceptions."""
        renderer = ui.RichConsoleRenderer(force_terminal=False, no_color=True)
        renderer.start_streaming()
        renderer.show_assistant_text("Hello", streaming=True)
        renderer.show_assistant_text(" world", streaming=True)
        renderer.end_streaming()
        # No assertion - just verifying no exceptions


class TestRendererInterface:
    """Tests verifying Renderer interface compliance."""

    @_pytest.fixture(params=["plain", "json", "rich"])
    def renderer(self, request: _pytest.FixtureRequest) -> ui.Renderer:
        """Provide different renderer implementations."""
        if request.param == "plain":
            return ui.PlainTextRenderer(output=_io.StringIO(), error=_io.StringIO())
        elif request.param == "json":
            return ui.JSONRenderer(output=_io.StringIO())
        else:
            return ui.RichConsoleRenderer(force_terminal=False, no_color=True)

    def test_all_renderers_implement_interface(self, renderer: ui.Renderer) -> None:
        """All renderers should implement the base interface."""
        # All these should work without raising
        renderer.show_user_message("test")
        renderer.show_assistant_text("response")
        renderer.show_info("info")
        renderer.show_error("error")

        tool_call = ui.ToolCallDisplay(tool_name="Test", tool_input={})
        renderer.show_tool_call(tool_call)

        result = tools_base.ToolResult(success=True, output="out", error=None)
        result_display = ui.ToolResultDisplay(tool_name="Test", result=result)
        renderer.show_tool_result(result_display)

        renderer.start_streaming()
        renderer.show_assistant_text("streaming", streaming=True)
        renderer.end_streaming()

        renderer.prompt_permission(tool_call, auto_approve=True)
        renderer.finalize()

