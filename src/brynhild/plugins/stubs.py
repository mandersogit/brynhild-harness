"""
Stub classes for standalone plugin testing.

These stubs allow plugin developers to test their tools without having
Brynhild installed. Import from this module when brynhild.tools.base
is not available.

Usage in plugin tools:

    try:
        import brynhild.tools.base as _base
        ToolResult = _base.ToolResult
        ToolBase = _base.Tool
    except ImportError:
        import brynhild.plugins.stubs as _stubs
        ToolResult = _stubs.ToolResult
        ToolBase = _stubs.ToolBase

Or, if brynhild isn't installed at all:

    try:
        import brynhild.tools.base as _base
        ToolResult = _base.ToolResult
        ToolBase = _base.Tool
    except ImportError:
        # Copy these classes inline for standalone testing
        import dataclasses as _dataclasses

        @_dataclasses.dataclass
        class ToolResult:
            success: bool
            output: str
            error: str | None = None

        class ToolBase:
            pass
"""

from __future__ import annotations

import dataclasses as _dataclasses
import typing as _typing


@_dataclasses.dataclass
class ToolResult:
    """
    Result of executing a tool.

    This is a standalone stub compatible with brynhild.tools.base.ToolResult.
    Use this for testing plugins without Brynhild installed.

    Attributes:
        success: Whether the operation succeeded.
        output: The tool's output (shown to the LLM).
        error: Error message if success=False.
    """

    success: bool
    output: str
    error: str | None = None

    def to_dict(self) -> dict[str, _typing.Any]:
        """Convert to JSON-serializable dict."""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
        }


class ToolBase:
    """
    Base class stub for plugin tools.

    This provides minimal implementations of methods that the real
    brynhild.tools.base.Tool provides. Plugin tools should inherit
    from this when Brynhild is not installed.

    Your Tool class must implement:
        - name (property): Tool identifier
        - description (property): Human-readable description
        - input_schema (property): JSON Schema for input
        - execute(input: dict) -> ToolResult: Tool implementation

    Optional overrides:
        - requires_permission (property): Default True
    """

    @property
    def name(self) -> str:
        """Tool name (must override)."""
        raise NotImplementedError("Tool must implement 'name' property")

    @property
    def description(self) -> str:
        """Tool description (must override)."""
        raise NotImplementedError("Tool must implement 'description' property")

    @property
    def requires_permission(self) -> bool:
        """Whether tool requires user permission (default True)."""
        return True

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        """JSON schema for tool input (must override)."""
        raise NotImplementedError("Tool must implement 'input_schema' property")

    async def execute(
        self,
        input: dict[str, _typing.Any],
    ) -> ToolResult:
        """Execute the tool (must override)."""
        raise NotImplementedError("Tool must implement 'execute' method")

    def to_api_format(self) -> dict[str, _typing.Any]:
        """
        Convert to Anthropic API tool format.

        This format is used when sending tool definitions to the LLM.
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def to_openai_format(self) -> dict[str, _typing.Any]:
        """
        Convert to OpenAI/OpenRouter API format.

        OpenAI uses a slightly different schema structure.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    def __repr__(self) -> str:
        return f"<Tool {self.name}>"


# Aliases for compatibility
Tool = ToolBase

__all__ = ["ToolResult", "ToolBase", "Tool"]

