"""Tests for hook pattern matching."""

import brynhild.hooks.matching as matching


class TestPatternMatcher:
    """Tests for PatternMatcher class."""

    def test_empty_patterns_always_match(self) -> None:
        """Empty patterns match any context."""
        matcher = matching.PatternMatcher({})
        assert matcher.matches({}) is True
        assert matcher.matches({"tool": "Bash"}) is True

    def test_exact_string_match(self) -> None:
        """Exact string patterns match exactly."""
        matcher = matching.PatternMatcher({"tool": "Bash"})
        assert matcher.matches({"tool": "Bash"}) is True
        assert matcher.matches({"tool": "Read"}) is False
        assert matcher.matches({"tool": "bash"}) is False  # Case sensitive

    def test_regex_match_caret(self) -> None:
        """Regex pattern with ^ matches start of string."""
        matcher = matching.PatternMatcher({"command": "^sudo"})
        assert matcher.matches({"command": "sudo rm -rf"}) is True
        assert matcher.matches({"command": "not sudo"}) is False

    def test_regex_match_dollar(self) -> None:
        """Regex pattern with $ matches end of string."""
        matcher = matching.PatternMatcher({"file": r"\.py$"})
        assert matcher.matches({"file": "test.py"}) is True
        assert matcher.matches({"file": "test.pyc"}) is False

    def test_regex_match_complex(self) -> None:
        """Complex regex patterns work correctly."""
        matcher = matching.PatternMatcher({"command": r"rm\s+-rf\s+/"})
        assert matcher.matches({"command": "rm -rf /"}) is True
        assert matcher.matches({"command": "rm -rf /home"}) is True
        assert matcher.matches({"command": "rm file.txt"}) is False

    def test_glob_match_star(self) -> None:
        """Glob pattern with * matches any characters."""
        matcher = matching.PatternMatcher({"file": "*.py"})
        assert matcher.matches({"file": "test.py"}) is True
        assert matcher.matches({"file": "module.py"}) is True
        assert matcher.matches({"file": "test.txt"}) is False

    def test_glob_match_question(self) -> None:
        """Glob pattern with ? matches single character."""
        matcher = matching.PatternMatcher({"code": "a?c"})
        assert matcher.matches({"code": "abc"}) is True
        assert matcher.matches({"code": "aXc"}) is True
        assert matcher.matches({"code": "abbc"}) is False

    def test_boolean_match_true(self) -> None:
        """Boolean pattern matches boolean values."""
        matcher = matching.PatternMatcher({"success": True})
        assert matcher.matches({"success": True}) is True
        assert matcher.matches({"success": False}) is False

    def test_boolean_match_false(self) -> None:
        """Boolean pattern False matches False."""
        matcher = matching.PatternMatcher({"success": False})
        assert matcher.matches({"success": False}) is True
        assert matcher.matches({"success": True}) is False

    def test_nested_field_access(self) -> None:
        """Dotted paths access nested fields."""
        matcher = matching.PatternMatcher({"tool_input.command": "ls"})
        assert matcher.matches({"tool_input": {"command": "ls"}}) is True
        assert matcher.matches({"tool_input": {"command": "pwd"}}) is False

    def test_nested_field_access_deep(self) -> None:
        """Deeply nested paths work."""
        matcher = matching.PatternMatcher({"a.b.c": "value"})
        assert matcher.matches({"a": {"b": {"c": "value"}}}) is True
        assert matcher.matches({"a": {"b": {"c": "other"}}}) is False

    def test_nested_field_missing_returns_false(self) -> None:
        """Missing nested fields don't match."""
        matcher = matching.PatternMatcher({"a.b.c": "value"})
        assert matcher.matches({"a": {"b": {}}}) is False
        assert matcher.matches({"a": {}}) is False
        assert matcher.matches({}) is False

    def test_multiple_patterns_all_must_match(self) -> None:
        """Multiple patterns use AND logic."""
        matcher = matching.PatternMatcher({
            "tool": "Bash",
            "tool_input.command": "^ls",
        })
        assert matcher.matches({
            "tool": "Bash",
            "tool_input": {"command": "ls -la"},
        }) is True
        assert matcher.matches({
            "tool": "Bash",
            "tool_input": {"command": "pwd"},
        }) is False
        assert matcher.matches({
            "tool": "Read",
            "tool_input": {"command": "ls -la"},
        }) is False

    def test_none_value_does_not_match(self) -> None:
        """None values don't match any pattern."""
        matcher = matching.PatternMatcher({"tool": "Bash"})
        assert matcher.matches({"tool": None}) is False

    def test_numeric_match(self) -> None:
        """Numeric patterns match numeric values."""
        matcher = matching.PatternMatcher({"count": 5})
        assert matcher.matches({"count": 5}) is True
        assert matcher.matches({"count": 6}) is False
        assert matcher.matches({"count": 5.0}) is True  # int/float equality


class TestMatchPatterns:
    """Tests for match_patterns convenience function."""

    def test_convenience_function(self) -> None:
        """match_patterns function works correctly."""
        assert matching.match_patterns({"tool": "Bash"}, {"tool": "Bash"}) is True
        assert matching.match_patterns({"tool": "Bash"}, {"tool": "Read"}) is False

