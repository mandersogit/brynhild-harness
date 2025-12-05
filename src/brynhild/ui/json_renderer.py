"""
JSON renderer (Layer 2).

Outputs machine-readable JSON for automation and scripting.
Accumulates all events and outputs a single JSON object at the end.
"""

import json as _json
import sys as _sys
import typing as _typing

import brynhild.ui.base as base


class JSONRenderer(base.Renderer):
    """
    JSON output renderer.

    Accumulates all conversation events and outputs a single JSON object
    when finalize() is called. This is ideal for scripting and automation.
    """

    def __init__(
        self,
        output: _typing.TextIO | None = None,
        *,
        indent: int = 2,
        show_cost: bool = False,
    ) -> None:
        """
        Initialize the JSON renderer.

        Args:
            output: Stream for output (default: sys.stdout).
            indent: JSON indentation level.
            show_cost: Accepted for consistency but JSON always includes cost data.
        """
        self._output = output or _sys.stdout
        self._indent = indent
        # JSON always includes cost if available (for programmatic use)
        _ = show_cost

        # Accumulate conversation data
        self._messages: list[dict[str, _typing.Any]] = []
        self._tool_calls: list[dict[str, _typing.Any]] = []
        self._tool_results: list[dict[str, _typing.Any]] = []
        self._errors: list[str] = []
        self._assistant_text = ""
        self._streaming = False
        self._finish_result: dict[str, _typing.Any] | None = None
        self._prompt_source: dict[str, _typing.Any] | None = None
        # Token tracking
        self._current_context_tokens = 0
        self._total_output_tokens = 0
        self._turn_output_tokens = 0
        self._is_streaming_mode = False
        # Cost tracking
        self._total_cost: float = 0.0
        self._reasoning_tokens: int = 0

    def show_prompt_source(self, sources: list[str], content: str) -> None:
        """Record the source(s) of a prompt."""
        self._prompt_source = {"sources": sources, "content": content}

    def show_user_message(self, content: str) -> None:
        """Record a user message."""
        self._messages.append({"role": "user", "content": content})

    def show_assistant_text(self, text: str, *, streaming: bool = False) -> None:
        """Record assistant text response."""
        if streaming:
            self._assistant_text += text
        else:
            if self._streaming:
                # End of streaming - text already accumulated
                pass
            else:
                self._assistant_text = text

    def show_tool_call(self, tool_call: base.ToolCallDisplay) -> None:
        """Record a tool call."""
        call_data: dict[str, _typing.Any] = {
            "tool": tool_call.tool_name,
            "input": tool_call.tool_input,
            "recovered": tool_call.is_recovered,
        }
        if tool_call.tool_id:
            call_data["id"] = tool_call.tool_id
        self._tool_calls.append(call_data)

    def show_tool_result(self, result: base.ToolResultDisplay) -> None:
        """Record a tool result."""
        result_data: dict[str, _typing.Any] = {
            "tool": result.tool_name,
            "success": result.result.success,
            "output": result.result.output,
        }
        if result.tool_id:
            result_data["id"] = result.tool_id
        if result.result.error:
            result_data["error"] = result.result.error
        self._tool_results.append(result_data)

    def show_error(self, error: str) -> None:
        """Record an error."""
        self._errors.append(error)

    def show_info(self, message: str) -> None:
        """Info messages are not included in JSON output."""
        # Could add to a separate "info" field if needed
        pass

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
        if reasoning_tokens is not None:
            self._reasoning_tokens += reasoning_tokens

    def set_streaming_mode(self, is_streaming: bool) -> None:
        """Set streaming mode for token tracking."""
        self._is_streaming_mode = is_streaming
        if is_streaming:
            self._turn_output_tokens = 0

    def update_turn_tokens(self, count: int) -> None:
        """Update per-turn token count (client-side estimate, temporary)."""
        self._turn_output_tokens = count

    def start_streaming(self) -> None:
        """Called when streaming response starts."""
        self._streaming = True

    def end_streaming(self) -> None:
        """Called when streaming response ends."""
        self._streaming = False

    def prompt_permission(
        self,
        _tool_call: base.ToolCallDisplay,
        *,
        auto_approve: bool = False,
    ) -> bool:
        """Permission handling for JSON mode."""
        # In JSON mode, we can't prompt interactively
        # Auto-approve if flag is set, otherwise deny
        return auto_approve

    def show_finish(
        self,
        status: str,
        summary: str,
        next_steps: str | None = None,
    ) -> None:
        """Record finish result for JSON output."""
        self._finish_result = {
            "status": status,
            "summary": summary,
        }
        if next_steps:
            self._finish_result["next_steps"] = next_steps

    def finalize(self, result: dict[str, _typing.Any] | None = None) -> None:
        """Output the accumulated JSON result."""
        output_data: dict[str, _typing.Any] = {}

        # Add result data if provided (provider info, usage, etc.)
        if result:
            output_data.update(result)

        # Add accumulated conversation data
        if self._assistant_text:
            output_data["response"] = self._assistant_text

        if self._messages:
            output_data["messages"] = self._messages

        if self._tool_calls:
            output_data["tool_calls"] = self._tool_calls

        if self._tool_results:
            output_data["tool_results"] = self._tool_results

        if self._finish_result:
            output_data["finish"] = self._finish_result

        if self._prompt_source:
            output_data["prompt_source"] = self._prompt_source

        if self._errors:
            if len(self._errors) == 1:
                output_data["error"] = self._errors[0]
            else:
                output_data["errors"] = self._errors

        # Add cost tracking if available
        if self._total_cost > 0:
            output_data["cost_usd"] = self._total_cost
        if self._reasoning_tokens > 0:
            output_data["reasoning_tokens"] = self._reasoning_tokens

        # Output JSON
        self._output.write(_json.dumps(output_data, indent=self._indent))
        self._output.write("\n")
        self._output.flush()

    def reset(self) -> None:
        """Reset accumulated data for a new conversation."""
        self._messages = []
        self._tool_calls = []
        self._tool_results = []
        self._errors = []
        self._assistant_text = ""
        self._streaming = False
        self._finish_result = None  # Don't forget to reset this!
        self._prompt_source = None
        self._current_context_tokens = 0
        self._total_output_tokens = 0
        self._turn_output_tokens = 0
        self._is_streaming_mode = False
        self._total_cost = 0.0
        self._reasoning_tokens = 0

