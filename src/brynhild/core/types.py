"""
Core data types for Brynhild.

These are data transfer objects (DTOs) used across the system.
They contain no UI logic - just structured data.
"""

import dataclasses as _dataclasses
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
    Format a tool result for inclusion in the message history.

    This creates the dict structure expected by the LLM API for tool results.

    Args:
        tool_use_id: The ID of the tool use this result is for.
        result: The tool result.

    Returns:
        Dict suitable for adding to message history content.
    """
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": result.output if result.success else result.error,
        "is_error": not result.success,
    }

