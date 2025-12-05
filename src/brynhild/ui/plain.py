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
        *,
        show_cost: bool = False,
    ) -> None:
        """
        Initialize the plain text renderer.

        Args:
            output: Stream for normal output (default: sys.stdout).
            error: Stream for error output (default: sys.stderr).
            show_cost: If True, display cost information.
        """
        self._output = output or _sys.stdout
        self._error = error or _sys.stderr
        self._streaming = False
        self._stream_buffer = ""
        self._stream_header_printed = False  # Track if we've printed "Assistant:"
        self._show_cost = show_cost
        # Token tracking
        self._current_context_tokens = 0
        self._total_output_tokens = 0
        self._turn_output_tokens = 0
        self._is_streaming_mode = False
        # Cost tracking
        self._total_cost: float = 0.0

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

    def show_prompt_source(self, file_paths: list[str], content: str) -> None:
        """Display the source of a prompt read from file(s)."""
        # Truncate content for display
        max_display_chars = 1000
        display_content = content
        if len(content) > max_display_chars:
            display_content = content[:max_display_chars] + "... (truncated)"
        # Format source info
        if len(file_paths) == 1:
            source_info = file_paths[0]
        else:
            source_info = ", ".join(file_paths)
        self._output.write(f"[Prompt from {source_info}]\n{display_content}\n")
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

    def update_token_counts(self, input_tokens: int, output_tokens: int) -> None:
        """Update provider-reported token counts (authoritative)."""
        self._current_context_tokens = input_tokens
        self._total_output_tokens = output_tokens

    def update_cost(
        self,
        cost: float | None,
        reasoning_tokens: int | None = None,
    ) -> None:
        """Update cost tracking from provider usage details."""
        if cost is not None:
            self._total_cost += cost
        # reasoning_tokens not displayed in plain text (too verbose)
        _ = reasoning_tokens

    def set_streaming_mode(self, is_streaming: bool) -> None:
        """Set streaming mode for token display."""
        self._is_streaming_mode = is_streaming
        if is_streaming:
            self._turn_output_tokens = 0

    def update_turn_tokens(self, count: int) -> None:
        """Update per-turn token count (client-side estimate, temporary)."""
        self._turn_output_tokens = count

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
            cost_str = ""
            if self._show_cost and self._total_cost > 0:
                if self._total_cost < 0.0001:
                    cost_str = f" | ${self._total_cost:.2e}"
                elif self._total_cost < 0.01:
                    cost_str = f" | ${self._total_cost:.4f}"
                else:
                    cost_str = f" | ${self._total_cost:.2f}"
            self._output.write(
                f"\nTokens: {usage.get('input_tokens', 0)} in / "
                f"{usage.get('output_tokens', 0)} out{cost_str}\n"
            )
            self._output.flush()

    def show_finish(
        self,
        status: str,
        summary: str,
        next_steps: str | None = None,
    ) -> None:
        """Display finish status when agent calls the Finish tool."""
        status_icons = {
            "success": "✅",
            "partial": "⚠️",
            "failed": "❌",
            "blocked": "🚧",
        }
        icon = status_icons.get(status, "ℹ️")

        self._output.write(f"\n{icon} Task Finished ({status})\n")
        self._output.write(f"Summary: {summary}\n")
        if next_steps:
            self._output.write(f"Next steps: {next_steps}\n")
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

