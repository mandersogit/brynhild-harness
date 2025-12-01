"""
Pattern matching engine for hook conditions.

Hooks can specify match conditions to filter when they fire. This module
provides the pattern matching logic for:
- Exact string matches
- Regex matches
- Glob patterns
- Boolean matches
- Nested field access (e.g., "tool_input.command")
"""

from __future__ import annotations

import contextlib as _contextlib
import fnmatch as _fnmatch
import re as _re
import typing as _typing


class PatternMatcher:
    """
    Matches patterns against context values.

    Supports multiple pattern types:
    - Exact: "Bash" matches "Bash"
    - Regex: "^sudo.*" matches "sudo rm -rf"
    - Glob: "*.py" matches "test.py"
    - Boolean: true/false matches boolean values
    """

    def __init__(self, patterns: dict[str, _typing.Any]) -> None:
        """
        Initialize with match patterns.

        Args:
            patterns: Dict of field paths to pattern values.
                      Field paths can be dotted for nested access.
                      e.g., {"tool": "Bash", "tool_input.command": "^rm.*"}
        """
        self._patterns = patterns
        self._compiled: dict[str, _re.Pattern[str]] = {}

        # Pre-compile regex patterns
        for key, value in patterns.items():
            if isinstance(value, str) and self._looks_like_regex(value):
                with _contextlib.suppress(_re.error):
                    self._compiled[key] = _re.compile(value)

    @staticmethod
    def _looks_like_regex(value: str) -> bool:
        """
        Check if a string looks like a regex pattern.

        We only treat patterns as regex if they have characters that are
        clearly regex-specific (not glob). This avoids treating `*.py` or
        `file?.txt` as regex when they're meant to be globs.

        Regex-specific: ^, $, +, (, ), |, \\, [, ]
        Shared with glob: *, ?
        """
        # Only these chars indicate regex (not shared with glob)
        regex_only_chars = {"^", "$", "+", "(", ")", "|", "\\", "[", "]"}
        return any(c in value for c in regex_only_chars)

    def matches(self, context: dict[str, _typing.Any]) -> bool:
        """
        Check if all patterns match the given context.

        All patterns must match (AND logic). If patterns is empty,
        always returns True.

        Args:
            context: Dict of context values to match against.
                     Should be the output of HookContext.to_dict().

        Returns:
            True if all patterns match, False otherwise.
        """
        if not self._patterns:
            return True

        for field_path, pattern in self._patterns.items():
            value = self._get_nested_value(context, field_path)
            if not self._match_value(field_path, pattern, value):
                return False

        return True

    def _get_nested_value(
        self,
        data: dict[str, _typing.Any],
        path: str,
    ) -> _typing.Any:
        """
        Get a nested value from a dict using dot notation.

        Args:
            data: Dict to traverse
            path: Dot-separated path (e.g., "tool_input.command")

        Returns:
            The value at the path, or None if not found.
        """
        parts = path.split(".")
        current: _typing.Any = data

        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None

        return current

    def _match_value(
        self,
        field_path: str,
        pattern: _typing.Any,
        value: _typing.Any,
    ) -> bool:
        """
        Match a single pattern against a value.

        Args:
            field_path: The field path (for looking up compiled regex)
            pattern: The pattern to match
            value: The value to match against

        Returns:
            True if pattern matches value.
        """
        if value is None:
            return False

        # Boolean match
        if isinstance(pattern, bool):
            return bool(value == pattern)

        # String pattern against string value
        if isinstance(pattern, str) and isinstance(value, str):
            # Try compiled regex first
            if field_path in self._compiled:
                return bool(self._compiled[field_path].search(value))

            # Try glob pattern
            if "*" in pattern or "?" in pattern:
                return _fnmatch.fnmatch(value, pattern)

            # Exact match
            return pattern == value

        # Number match
        if isinstance(pattern, (int, float)) and isinstance(value, (int, float)):
            return pattern == value

        # Fallback: string comparison
        return str(pattern) == str(value)


def match_patterns(
    patterns: dict[str, _typing.Any],
    context: dict[str, _typing.Any],
) -> bool:
    """
    Convenience function to match patterns against context.

    Args:
        patterns: Dict of field paths to pattern values.
        context: Dict of context values.

    Returns:
        True if all patterns match.
    """
    return PatternMatcher(patterns).matches(context)

