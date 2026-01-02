"""
Test tool for entry point discovery integration tests.

This tool demonstrates a minimal working tool that can be loaded
via the 'brynhild.tools' entry point.
"""

from __future__ import annotations

import typing as _typing

# Import brynhild types for ToolResult
# This import works because this package depends on brynhild being installed
import brynhild.tools.base as _base


class Tool(_base.Tool):
    """
    A simple calculator tool for testing entry point discovery.

    This tool evaluates safe mathematical expressions.
    """

    @property
    def name(self) -> str:
        return "TestCalculator"

    @property
    def description(self) -> str:
        return "A test calculator that evaluates simple math expressions (addition only for safety)"

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {
            "type": "object",
            "properties": {
                "a": {
                    "type": "number",
                    "description": "First number",
                },
                "b": {
                    "type": "number",
                    "description": "Second number",
                },
            },
            "required": ["a", "b"],
        }

    @property
    def requires_permission(self) -> bool:
        # Safe read-only calculation
        return False

    async def execute(self, input: dict[str, _typing.Any]) -> _base.ToolResult:
        """Execute the calculator."""
        a = input.get("a")
        b = input.get("b")

        if a is None or b is None:
            return _base.ToolResult(
                success=False,
                output="",
                error="Both 'a' and 'b' are required",
            )

        try:
            result = float(a) + float(b)
            return _base.ToolResult(
                success=True,
                output=f"{a} + {b} = {result}",
            )
        except (TypeError, ValueError) as e:
            return _base.ToolResult(
                success=False,
                output="",
                error=f"Invalid input: {e}",
            )
