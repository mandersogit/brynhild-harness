"""
Test tool that adds markers to prove it's being used.

This tool doesn't do anything useful - it just returns a marker
string to prove the plugin tool system is working.
"""

from __future__ import annotations

import typing as _typing


class Tool:
    """Marker tool for testing plugin tool loading."""

    name = "marker"
    description = "Returns a marker string to prove plugin tools work"

    # Track how many times the tool has been called
    _call_count = 0

    # Schema for the tool
    input_schema = {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Optional message to include in response",
            },
        },
        "required": [],
    }

    def __init__(self) -> None:
        """Initialize the tool."""
        pass

    async def execute(
        self,
        message: str = "",
        **kwargs: _typing.Any,  # noqa: ARG002 - API compatibility
    ) -> dict[str, _typing.Any]:
        """Execute the marker tool.

        Args:
            message: Optional message to include.

        Returns:
            Dict with output and success fields.
        """
        Tool._call_count += 1

        output = f"[PLUGIN-TOOL-MARKER] Call #{Tool._call_count}"
        if message:
            output += f" - Message: {message}"

        return {
            "output": output,
            "success": True,
        }

    def to_api_format(self) -> dict[str, _typing.Any]:
        """Return tool in Anthropic API format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def to_openai_format(self) -> dict[str, _typing.Any]:
        """Return tool in OpenAI API format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }
