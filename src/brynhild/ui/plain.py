"""
Plain text renderer (Layer 1).

Outputs simple text to stdout with no formatting or colors.
Fully testable and works in any terminal.
"""

import io as _io
import sys as _sys
import typing as _typing

import brynhild.ui.base as base
import brynhild.ui.icons as icons


class PlainTextRenderer(base.Renderer):
    """
    Simple plain text renderer.

    Outputs to stdout (or a custom stream) with no ANSI codes or formatting.
    This is the most basic renderer, suitable for piped output and testing.
    """

    def __init__(
        self,
        output: _typing.TextIO | None = None,
        error: _typing.TextIO | None = None,
    ) -> None:
        """
        Initialize the plain text renderer.

        Args:
            output: Stream for normal output (default: sys.stdout).
            error: Stream for error output (default: sys.stderr).
        """
        self._output = output or _sys.stdout
        self._error = error or _sys.stderr
        self._streaming = False
        self._stream_buffer = ""
        self._stream_header_printed = False  # Track if we've printed "Assistant:"

    def show_session_banner(
        self,
        *,
        model: str,
        provider: str,
        profile: str | None = None,
        session: str | None = None,
    ) -> None:
        """Display session info banner."""
        profile_str = profile if profile else "default"
        session_str = session if session and session != "new" else "new"
        self._output.write(
            f"[{model} ({provider}) | Profile: {profile_str} | Session: {session_str}]\n"
        )
        self._output.flush()

    def show_user_message(self, content: str) -> None:
        """Display a user message."""
        self._output.write(f"User: {content}\n")
        self._output.flush()

    def show_assistant_text(self, text: str, *, streaming: bool = False) -> None:
        """Display assistant text response."""
        if streaming:
            # Print "Assistant:" prefix on first text
            # (Whitespace filtering is done in RendererCallbacks)
            if not self._stream_header_printed:
                self._output.write("Assistant: ")
                self._stream_header_printed = True
            self._output.write(text)
            self._output.flush()
            self._stream_buffer += text
        else:
            # Complete message - add prefix if not streaming
            if not self._streaming:
                self._output.write(f"Assistant: {text}\n")
            else:
                # End of streaming - just add newline
                self._output.write("\n")
            self._output.flush()

    def show_tool_call(self, tool_call: base.ToolCallDisplay) -> None:
        """Display that a tool is being called."""
        if tool_call.is_recovered:
            self._output.write(
                f"[{icons.icon_recovered()}Tool (recovered): {tool_call.tool_name}]\n"
            )
        else:
            self._output.write(f"[{icons.icon_bolt()}Tool: {tool_call.tool_name}]\n")
        # Format input nicely for text output
        for key, value in tool_call.tool_input.items():
            if isinstance(value, str) and len(value) > 80:
                value = value[:77] + "..."
            self._output.write(f"  {key}: {value}\n")
        self._output.flush()

    def show_tool_result(self, result: base.ToolResultDisplay) -> None:
        """Display the result of a tool call."""
        if result.result.success:
            status = icons.icon_success()
        else:
            status = icons.icon_failure()
        self._output.write(f"[{status}{result.tool_name}]\n")

        if result.result.success:
            output = result.result.output
            # Truncate very long output
            if len(output) > 1000:
                output = output[:997] + "..."
            if output.strip():
                self._output.write(output)
                if not output.endswith("\n"):
                    self._output.write("\n")
        else:
            if result.result.error:
                self._output.write(f"Error: {result.result.error}\n")

        self._output.flush()

    def show_error(self, error: str) -> None:
        """Display an error message."""
        self._error.write(f"Error: {error}\n")
        self._error.flush()

    def show_info(self, message: str) -> None:
        """Display an informational message."""
        self._output.write(f"{message}\n")
        self._output.flush()

    def start_streaming(self) -> None:
        """Called when streaming response starts."""
        self._streaming = True
        self._stream_buffer = ""
        self._stream_header_printed = False

    def end_streaming(self) -> None:
        """Called when streaming response ends."""
        self._streaming = False
        # Only print newline if we printed the header (i.e., had content)
        if self._stream_header_printed:
            self._output.write("\n")
            self._output.flush()
        self._stream_header_printed = False

    def prompt_permission(
        self,
        tool_call: base.ToolCallDisplay,
        *,
        auto_approve: bool = False,
    ) -> bool:
        """Ask user for permission to execute a tool."""
        if auto_approve:
            return True

        # In plain text mode, we can't do interactive prompts reliably
        # Return False to be safe (use --yes flag for automation)
        self._output.write(f"[Permission required for {tool_call.tool_name}]\n")
        self._output.write("Use --yes flag to auto-approve, or run interactively.\n")
        self._output.flush()
        return False

    def finalize(self, result: dict[str, _typing.Any] | None = None) -> None:
        """Finalize output - show usage stats if available."""
        if result and "usage" in result:
            usage = result["usage"]
            self._output.write(
                f"\nTokens: {usage.get('input_tokens', 0)} in / "
                f"{usage.get('output_tokens', 0)} out\n"
            )
            self._output.flush()


class CaptureRenderer(PlainTextRenderer):
    """
    A renderer that captures output for testing.

    All output is written to internal StringIO buffers that can be inspected.
    """

    def __init__(self) -> None:
        """Initialize with internal capture buffers."""
        self._captured_output = _io.StringIO()
        self._captured_error = _io.StringIO()
        super().__init__(output=self._captured_output, error=self._captured_error)

    def get_output(self) -> str:
        """Get all captured standard output."""
        return self._captured_output.getvalue()

    def get_error(self) -> str:
        """Get all captured error output."""
        return self._captured_error.getvalue()

    def clear(self) -> None:
        """Clear captured output."""
        self._captured_output = _io.StringIO()
        self._captured_error = _io.StringIO()
        self._output = self._captured_output
        self._error = self._captured_error

