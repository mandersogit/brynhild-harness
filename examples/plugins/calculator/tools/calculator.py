"""
Calculator tool for evaluating mathematical expressions.

This is an example plugin tool demonstrating the correct interface.
See docs/plugin-tool-interface.md for the full specification.
"""

from __future__ import annotations

import math as _math
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


# Safe functions available for evaluation
SAFE_FUNCTIONS: dict[str, _typing.Callable[..., _typing.Any]] = {
    # Basic math
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "pow": pow,
    # Trigonometry
    "sin": _math.sin,
    "cos": _math.cos,
    "tan": _math.tan,
    "asin": _math.asin,
    "acos": _math.acos,
    "atan": _math.atan,
    "atan2": _math.atan2,
    # Exponential and logarithmic
    "sqrt": _math.sqrt,
    "exp": _math.exp,
    "log": _math.log,
    "log10": _math.log10,
    "log2": _math.log2,
    # Other
    "floor": _math.floor,
    "ceil": _math.ceil,
    "factorial": _math.factorial,
    "gcd": _math.gcd,
}

# Safe constants
SAFE_CONSTANTS: dict[str, float] = {
    "pi": _math.pi,
    "e": _math.e,
    "tau": _math.tau,
    "inf": _math.inf,
}


def safe_eval(expression: str) -> float | int:
    """
    Safely evaluate a mathematical expression.

    Only allows basic arithmetic, safe functions, and constants.
    No access to builtins, imports, or arbitrary code.

    Args:
        expression: Mathematical expression to evaluate.

    Returns:
        The result of the evaluation.

    Raises:
        ValueError: If expression contains forbidden operations.
        SyntaxError: If expression is invalid Python syntax.
    """
    # Create evaluation namespace with only safe items
    namespace: dict[str, _typing.Any] = {}
    namespace.update(SAFE_FUNCTIONS)
    namespace.update(SAFE_CONSTANTS)

    # Compile to check for syntax errors and forbidden operations
    try:
        code = compile(expression, "<expression>", "eval")
    except SyntaxError as e:
        raise SyntaxError(f"Invalid expression: {e}") from e

    # Check for forbidden names
    for name in code.co_names:
        if name not in namespace:
            raise ValueError(f"Forbidden name: {name}")

    # Evaluate with restricted namespace
    try:
        result = eval(code, {"__builtins__": {}}, namespace)
    except Exception as e:
        raise ValueError(f"Evaluation error: {e}") from e

    return result  # type: ignore[no-any-return]


class Tool(ToolBase):
    """
    Calculator tool for evaluating mathematical expressions.

    Supports basic arithmetic, trigonometry, and common math functions.
    Uses safe evaluation to prevent arbitrary code execution.
    """

    @property
    def name(self) -> str:
        """Tool name."""
        return "calculator"

    @property
    def description(self) -> str:
        """Tool description for the LLM."""
        return (
            "Evaluate mathematical expressions. "
            "Supports: +, -, *, /, **, %, and functions like "
            "sqrt(), sin(), cos(), log(), abs(), round(). "
            "Constants: pi, e, tau."
        )

    @property
    def requires_permission(self) -> bool:
        """Calculator is safe and doesn't require permission."""
        return False

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        """JSON schema for tool input."""
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": (
                        "Mathematical expression to evaluate. "
                        "Examples: '2 + 2', 'sqrt(16)', 'sin(pi/2)'"
                    ),
                },
            },
            "required": ["expression"],
        }

    def __init__(self) -> None:
        """Initialize the calculator tool."""
        pass

    async def execute(
        self,
        input: dict[str, _typing.Any],
    ) -> ToolResult:
        """
        Execute the calculator.

        Args:
            input: Dictionary with 'expression' key.

        Returns:
            ToolResult with the calculation result.
        """
        expression = input.get("expression", "")

        # Validate input
        if not expression:
            return ToolResult(
                success=False,
                output="",
                error="expression is required",
            )

        if not isinstance(expression, str):
            return ToolResult(
                success=False,
                output="",
                error="expression must be a string",
            )

        # Limit expression length
        if len(expression) > 1000:
            return ToolResult(
                success=False,
                output="",
                error="expression too long (max 1000 characters)",
            )

        # Evaluate
        try:
            result = safe_eval(expression)
            return ToolResult(
                success=True,
                output=f"Result: {result}",
            )
        except SyntaxError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Syntax error: {e}",
            )
        except ValueError as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )
        except ZeroDivisionError:
            return ToolResult(
                success=False,
                output="",
                error="Division by zero",
            )
        except OverflowError:
            return ToolResult(
                success=False,
                output="",
                error="Result too large",
            )

