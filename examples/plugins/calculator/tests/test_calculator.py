"""
Tests for the calculator tool.

These tests can run standalone (without brynhild installed) thanks to
the try/except import pattern in the tool module.
"""

from __future__ import annotations

import math as _math
import sys as _sys
import pathlib as _pathlib

import pytest as _pytest

# Add parent directory to path for imports
_sys.path.insert(0, str(_pathlib.Path(__file__).parent.parent))

from tools.calculator import Tool, safe_eval, SAFE_FUNCTIONS, SAFE_CONSTANTS


class TestSafeEval:
    """Tests for the safe_eval function."""

    def test_basic_arithmetic(self) -> None:
        """Basic arithmetic operations work."""
        assert safe_eval("2 + 2") == 4
        assert safe_eval("10 - 3") == 7
        assert safe_eval("4 * 5") == 20
        assert safe_eval("15 / 3") == 5.0
        assert safe_eval("2 ** 8") == 256
        assert safe_eval("17 % 5") == 2

    def test_parentheses(self) -> None:
        """Parentheses work correctly."""
        assert safe_eval("(2 + 3) * 4") == 20
        assert safe_eval("2 + (3 * 4)") == 14
        assert safe_eval("((1 + 2) * (3 + 4))") == 21

    def test_math_functions(self) -> None:
        """Math functions work correctly."""
        assert safe_eval("sqrt(16)") == 4.0
        assert safe_eval("abs(-5)") == 5
        assert _math.isclose(safe_eval("sin(0)"), 0.0)
        assert _math.isclose(safe_eval("cos(0)"), 1.0)
        assert _math.isclose(safe_eval("log(e)"), 1.0)

    def test_constants(self) -> None:
        """Constants are available."""
        assert _math.isclose(safe_eval("pi"), _math.pi)
        assert _math.isclose(safe_eval("e"), _math.e)
        assert _math.isclose(safe_eval("tau"), _math.tau)

    def test_complex_expressions(self) -> None:
        """Complex expressions work."""
        assert _math.isclose(safe_eval("sin(pi/2)"), 1.0)
        assert safe_eval("2 * sqrt(16) + 3") == 11.0
        assert safe_eval("max(1, 2, 3)") == 3
        assert safe_eval("min(5, 3, 7)") == 3

    def test_forbidden_names_rejected(self) -> None:
        """Forbidden names raise ValueError."""
        with _pytest.raises(ValueError, match="Forbidden name"):
            safe_eval("__import__('os')")

        with _pytest.raises(ValueError, match="Forbidden name"):
            safe_eval("open('/etc/passwd')")

        with _pytest.raises(ValueError, match="Forbidden name"):
            safe_eval("eval('1+1')")

    def test_syntax_errors(self) -> None:
        """Invalid syntax raises SyntaxError."""
        with _pytest.raises(SyntaxError):
            safe_eval("2 +")

        with _pytest.raises(SyntaxError):
            safe_eval("(2 + 3")


class TestCalculatorTool:
    """Tests for the Calculator tool class."""

    def test_name_and_description(self) -> None:
        """Tool has correct metadata."""
        tool = Tool()
        assert tool.name == "calculator"
        assert "expression" in tool.description.lower()
        assert "sqrt" in tool.description.lower()

    def test_requires_no_permission(self) -> None:
        """Calculator is safe and doesn't require permission."""
        tool = Tool()
        assert tool.requires_permission is False

    def test_input_schema_valid(self) -> None:
        """Input schema is valid JSON Schema."""
        tool = Tool()
        schema = tool.input_schema
        assert schema["type"] == "object"
        assert "expression" in schema["properties"]
        assert "expression" in schema["required"]

    @_pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        """Tool executes successfully with valid input."""
        tool = Tool()
        result = await tool.execute({"expression": "2 + 2"})
        assert result.success is True
        assert "4" in result.output

    @_pytest.mark.asyncio
    async def test_execute_missing_expression(self) -> None:
        """Tool returns error for missing expression."""
        tool = Tool()
        result = await tool.execute({})
        assert result.success is False
        assert result.error is not None
        assert "required" in result.error.lower()

    @_pytest.mark.asyncio
    async def test_execute_empty_expression(self) -> None:
        """Tool returns error for empty expression."""
        tool = Tool()
        result = await tool.execute({"expression": ""})
        assert result.success is False
        assert result.error is not None

    @_pytest.mark.asyncio
    async def test_execute_invalid_expression(self) -> None:
        """Tool returns error for invalid expression."""
        tool = Tool()
        result = await tool.execute({"expression": "2 +"})
        assert result.success is False
        assert result.error is not None
        assert "syntax" in result.error.lower()

    @_pytest.mark.asyncio
    async def test_execute_forbidden_name(self) -> None:
        """Tool returns error for forbidden operations."""
        tool = Tool()
        result = await tool.execute({"expression": "__import__('os')"})
        assert result.success is False
        assert result.error is not None
        assert "forbidden" in result.error.lower()

    @_pytest.mark.asyncio
    async def test_execute_division_by_zero(self) -> None:
        """Tool handles division by zero."""
        tool = Tool()
        result = await tool.execute({"expression": "1 / 0"})
        assert result.success is False
        assert result.error is not None
        assert "zero" in result.error.lower()

    @_pytest.mark.asyncio
    async def test_execute_too_long(self) -> None:
        """Tool rejects overly long expressions."""
        tool = Tool()
        result = await tool.execute({"expression": "1 + " * 500})
        assert result.success is False
        assert result.error is not None
        assert "long" in result.error.lower()

    @_pytest.mark.asyncio
    async def test_execute_math_functions(self) -> None:
        """Tool correctly evaluates math functions."""
        tool = Tool()

        result = await tool.execute({"expression": "sqrt(144)"})
        assert result.success is True
        assert "12" in result.output

        result = await tool.execute({"expression": "factorial(5)"})
        assert result.success is True
        assert "120" in result.output


class TestSafeFunctionsAndConstants:
    """Tests for the safe functions and constants lists."""

    def test_all_functions_callable(self) -> None:
        """All safe functions are callable."""
        for name, func in SAFE_FUNCTIONS.items():
            assert callable(func), f"{name} is not callable"

    def test_all_constants_numeric(self) -> None:
        """All safe constants are numeric."""
        for name, value in SAFE_CONSTANTS.items():
            assert isinstance(value, (int, float)), f"{name} is not numeric"


if __name__ == "__main__":
    _pytest.main([__file__, "-v"])

