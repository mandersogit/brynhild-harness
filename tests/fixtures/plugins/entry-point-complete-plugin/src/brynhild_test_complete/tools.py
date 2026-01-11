"""
Test tools for entry point discovery integration tests.

Demonstrates tool registration via 'brynhild.tools' entry point.
"""

from __future__ import annotations

import typing as _typing

import brynhild.tools.base as _base


class EchoTool(_base.Tool):
    """
    A simple echo tool for testing entry point tool discovery.

    Returns whatever input it receives.
    """

    @property
    def name(self) -> str:
        return "TestEcho"

    @property
    def description(self) -> str:
        return "A test tool that echoes back its input (for testing entry point tool loading)"

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Message to echo back",
                },
            },
            "required": ["message"],
        }

    @property
    def requires_permission(self) -> bool:
        # Safe read-only tool
        return False

    async def execute(self, input: dict[str, _typing.Any]) -> _base.ToolResult:
        """Execute the echo tool."""
        message = input.get("message")

        if message is None:
            return _base.ToolResult(
                success=False,
                output="",
                error="'message' is required",
            )

        return _base.ToolResult(
            success=True,
            output=f"Echo: {message}",
        )


class CounterTool(_base.Tool):
    """
    A stateful counter tool for testing entry point tool discovery.

    Tracks a counter that persists across calls (within session).
    Tests that tool instances work correctly via entry points.
    """

    _counter: int = 0  # Class-level counter for testing

    @property
    def name(self) -> str:
        return "TestCounter"

    @property
    def description(self) -> str:
        return "A test counter tool that increments/decrements a value (for testing tool state)"

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["increment", "decrement", "get", "reset"],
                    "description": "Operation to perform",
                },
                "amount": {
                    "type": "integer",
                    "description": "Amount to increment/decrement by (default: 1)",
                    "default": 1,
                },
            },
            "required": ["operation"],
        }

    @property
    def requires_permission(self) -> bool:
        return False

    async def execute(self, input: dict[str, _typing.Any]) -> _base.ToolResult:
        """Execute the counter tool."""
        operation = input.get("operation")
        amount = input.get("amount", 1)

        if operation is None:
            return _base.ToolResult(
                success=False,
                output="",
                error="'operation' is required",
            )

        if operation == "increment":
            CounterTool._counter += amount
        elif operation == "decrement":
            CounterTool._counter -= amount
        elif operation == "reset":
            CounterTool._counter = 0
        elif operation != "get":
            return _base.ToolResult(
                success=False,
                output="",
                error=f"Unknown operation: {operation}",
            )

        return _base.ToolResult(
            success=True,
            output=f"Counter value: {CounterTool._counter}",
        )

