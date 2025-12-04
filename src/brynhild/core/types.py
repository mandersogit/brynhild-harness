"""
Core data types for Brynhild.

These are data transfer objects (DTOs) used across the system.
They contain no UI logic - just structured data.
"""

import dataclasses as _dataclasses
import json as _json
import typing as _typing

import brynhild.constants as _constants
import brynhild.tools.base as tools_base


@_dataclasses.dataclass
class ToolCallDisplay:
    """Information about a tool call for display/logging purposes."""

    tool_name: str
    tool_input: dict[str, _typing.Any]
    tool_id: str | None = None
    is_recovered: bool = False
    """Whether this tool call was recovered from thinking text (not native)."""


@_dataclasses.dataclass
class ToolResultDisplay:
    """Information about a tool result for display/logging purposes."""

    tool_name: str
    result: tools_base.ToolResult
    tool_id: str | None = None


def format_tool_result_message(
    tool_use_id: str,
    result: tools_base.ToolResult,
    *,
    max_chars: int | None = None,
) -> dict[str, _typing.Any]:
    """
    Format a tool result as a message for inclusion in message history.

    This creates a message with role "tool_result" that providers can convert
    to their native format (OpenAI: role "tool", Anthropic: user message with
    tool_result content blocks).

    Tool output is truncated if it exceeds max_chars to prevent context window
    overflow from runaway tool output (e.g., grep without limit).

    Args:
        tool_use_id: The ID of the tool use this result is for.
        result: The tool result.
        max_chars: Maximum characters for content (default: DEFAULT_TOOL_RESULT_MAX_CHARS).

    Returns:
        Message dict with role "tool_result" suitable for message history.
    """
    if max_chars is None:
        max_chars = _constants.DEFAULT_TOOL_RESULT_MAX_CHARS

    content = result.output if result.success else result.error
    if content and len(content) > max_chars:
        content = (
            content[:max_chars]
            + f"\n\n... [TRUNCATED: output exceeded {max_chars:,} characters] ..."
        )

    return {
        "role": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content,
        "is_error": not result.success,
    }


def format_assistant_tool_call(
    tool_uses: list[_typing.Any],
    content: str = "",
    *,
    thinking: str | None = None,
) -> dict[str, _typing.Any]:
    """
    Format an assistant message containing tool calls.

    This creates the assistant message that must precede tool result messages
    in OpenAI-compatible APIs. The tool_calls array allows the model to
    associate tool results with the calls it made.

    Args:
        tool_uses: List of ToolUse objects from the model's response.
        content: Optional text content from the assistant (may be empty).
        thinking: Optional thinking/reasoning content to prepend to content.
            When provided, the model's thinking is included in the message
            so it can "remember" its reasoning in subsequent turns.

    Returns:
        Assistant message dict with tool_calls array.
    """
    # Import here to avoid circular imports
    import brynhild.api.types as api_types

    tool_calls = []
    for tool_use in tool_uses:
        # Handle both ToolUse objects and raw dicts
        if isinstance(tool_use, api_types.ToolUse):
            tool_calls.append({
                "id": tool_use.id,
                "type": "function",
                "function": {
                    "name": tool_use.name,
                    "arguments": _json.dumps(tool_use.input),
                },
            })
        else:
            # Already a dict (shouldn't happen but handle gracefully)
            tool_calls.append(tool_use)

    # Build the message with reasoning as a separate field.
    # The provider's _format_messages() will convert this to the appropriate
    # format (reasoning_field, thinking_tags, or none) based on settings.
    message: dict[str, _typing.Any] = {
        "role": "assistant",
        "content": content,
        "tool_calls": tool_calls,
    }

    if thinking:
        message["reasoning"] = thinking

    return message

