"""
Test tool that adds markers to prove it's being used.

This tool demonstrates the CORRECT plugin tool interface.
See docs/plugin-tool-interface.md for the full specification.

WARNING: This is a test fixture, but it uses the production interface.
Copy this pattern when creating your own plugin tools.
"""

from __future__ import annotations

import typing as _typing

# Import from brynhild when available, use stubs for standalone testing
try:
    import brynhild.tools.base as _base

    ToolResult = _base.ToolResult
    ToolBase = _base.Tool
except ImportError:
    # Stubs for standalone testing without brynhild installed
    import dataclasses as _dataclasses

    @_dataclasses.dataclass
    class ToolResult:  # type: ignore[no-redef]
        """Result of executing a tool."""

        success: bool
        output: str
        error: str | None = None

    class ToolBase:  # type: ignore[no-redef]
        """Stub base class for testing."""

        pass


class Tool(ToolBase):
    """
    Marker tool for testing plugin tool loading.

    This tool doesn't do anything useful - it just returns a marker
    string to prove the plugin tool system is working.
    """

    # Track how many times the tool has been called (class variable)
    _call_count: _typing.ClassVar[int] = 0

    @property
    def name(self) -> str:
        """Tool name."""
        return "marker"

    @property
    def description(self) -> str:
        """Tool description for the LLM."""
        return "Returns a marker string to prove plugin tools work"

    @property
    def requires_permission(self) -> bool:
        """This tool is safe and doesn't require permission."""
        return False

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        """JSON schema for tool input."""
        return {
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
        input: dict[str, _typing.Any],
    ) -> ToolResult:
        """
        Execute the marker tool.

        Args:
            input: Dictionary matching the input schema.

        Returns:
            ToolResult with marker output.
        """
        Tool._call_count += 1
        message = input.get("message", "")

        output = f"[PLUGIN-TOOL-MARKER] Call #{Tool._call_count}"
        if message:
            output += f" - Message: {message}"

        return ToolResult(
            success=True,
            output=output,
        )
