"""
Example tools for the plugin template.

Each tool must be registered in pyproject.toml:

    [project.entry-points."brynhild.tools"]
    greeter = "brynhild_my_plugin.tools:GreeterTool"
    counter = "brynhild_my_plugin.tools:CounterTool"

The entry point value must be the Tool CLASS, not an instance.
"""

import typing as _typing

import brynhild.tools.base as _base


class GreeterTool(_base.Tool):
    """
    A simple greeting tool.

    Demonstrates the basic Tool interface with all required methods.
    """

    @property
    def name(self) -> str:
        """Tool name - must match the entry point name."""
        return "greeter"

    @property
    def description(self) -> str:
        """Description shown to the LLM."""
        return (
            "Generate a friendly greeting for a person. "
            "Use when the user wants to say hello to someone."
        )

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        """JSON schema for tool input."""
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The name of the person to greet",
                },
                "style": {
                    "type": "string",
                    "enum": ["formal", "casual", "enthusiastic"],
                    "description": "Greeting style (default: casual)",
                },
            },
            "required": ["name"],
        }

    @property
    def requires_permission(self) -> bool:
        """This tool is safe - no permission needed."""
        return False

    async def execute(
        self,
        input: dict[str, _typing.Any],
    ) -> _base.ToolResult:
        """Execute the greeting."""
        name = input.get("name", "friend")
        style = input.get("style", "casual")

        greetings = {
            "formal": f"Good day, {name}. It is a pleasure to meet you.",
            "casual": f"Hey {name}! What's up?",
            "enthusiastic": f"WOW! {name}!! SO GREAT to see you!!!",
        }

        greeting = greetings.get(style, greetings["casual"])

        return _base.ToolResult(
            success=True,
            output=greeting,
        )


class CounterTool(_base.Tool):
    """
    A stateful counter tool.

    Demonstrates how tools can maintain state between invocations.
    """

    def __init__(self) -> None:
        """Initialize counter to zero."""
        self._count = 0

    @property
    def name(self) -> str:
        return "counter"

    @property
    def description(self) -> str:
        return (
            "Manage a simple counter. "
            "Supports increment, decrement, get, and reset operations."
        )

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["increment", "decrement", "get", "reset"],
                    "description": "The operation to perform",
                },
                "amount": {
                    "type": "integer",
                    "description": "Amount to increment/decrement (default: 1)",
                },
            },
            "required": ["operation"],
        }

    @property
    def requires_permission(self) -> bool:
        return False

    async def execute(
        self,
        input: dict[str, _typing.Any],
    ) -> _base.ToolResult:
        """Execute counter operation."""
        operation = input.get("operation", "get")
        amount = input.get("amount", 1)

        if operation == "increment":
            self._count += amount
            return _base.ToolResult(
                success=True,
                output=f"Incremented by {amount}. Count is now {self._count}.",
            )
        elif operation == "decrement":
            self._count -= amount
            return _base.ToolResult(
                success=True,
                output=f"Decremented by {amount}. Count is now {self._count}.",
            )
        elif operation == "reset":
            self._count = 0
            return _base.ToolResult(
                success=True,
                output="Counter reset to 0.",
            )
        else:  # get
            return _base.ToolResult(
                success=True,
                output=f"Current count: {self._count}",
            )

