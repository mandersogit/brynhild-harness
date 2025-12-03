"""
Core data types for Brynhild.

These are data transfer objects (DTOs) used across the system.
They contain no UI logic - just structured data.
"""

import dataclasses as _dataclasses
import json as _json
import typing as _typing

import brynhild.tools.base as tools_base


@_dataclasses.dataclass
class ToolCallDisplay:
    """Information about a tool call for display/logging purposes."""

    tool_name: str
    tool_input: dict[str, _typing.Any]
    tool_id: str | None = None


@_dataclasses.dataclass
class ToolResultDisplay:
    """Information about a tool result for display/logging purposes."""

    tool_name: str
    result: tools_base.ToolResult
    tool_id: str | None = None


def format_tool_result_message(
    tool_use_id: str,
    result: tools_base.ToolResult,
) -> dict[str, _typing.Any]:
    """
    Format a tool result as a message for inclusion in message history.

    This creates a message with role "tool_result" that providers can convert
    to their native format (OpenAI: role "tool", Anthropic: user message with
    tool_result content blocks).

    Args:
        tool_use_id: The ID of the tool use this result is for.
        result: The tool result.

    Returns:
        Message dict with role "tool_result" suitable for message history.
    """
    return {
        "role": "tool_result",
        "tool_use_id": tool_use_id,
        "content": result.output if result.success else result.error,
        "is_error": not result.success,
    }


def format_assistant_tool_call(
    tool_uses: list[_typing.Any],
    content: str = "",
) -> dict[str, _typing.Any]:
    """
    Format an assistant message containing tool calls.

    This creates the assistant message that must precede tool result messages
    in OpenAI-compatible APIs. The tool_calls array allows the model to
    associate tool results with the calls it made.

    Args:
        tool_uses: List of ToolUse objects from the model's response.
        content: Optional text content from the assistant (may be empty).

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

    return {
        "role": "assistant",
        "content": content,
        "tool_calls": tool_calls,
    }

