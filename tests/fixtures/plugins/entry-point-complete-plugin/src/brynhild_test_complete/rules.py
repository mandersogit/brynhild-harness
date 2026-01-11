"""
Test rules for entry point discovery integration tests.

Demonstrates rules registration via 'brynhild.rules' entry point.
"""

from __future__ import annotations


def get_rules():
    """
    Get the rules for this plugin.

    Called automatically when Brynhild discovers rules via the
    'brynhild.rules' entry point.

    Can return:
        - A string (single rule content)
        - A list of strings (multiple rules)
        - A dict with 'content' key (and optional 'name')
    """
    return """
# Test Rules from Entry Point Plugin

These rules were loaded via the `brynhild.rules` entry point.

## Important Guidelines

1. Always acknowledge when the test rules are active
2. Reference this file when asked about active rules
3. Demonstrate that entry point rule loading works correctly

## Test Markers

- ENTRY_POINT_RULES_LOADED: true
- PLUGIN_NAME: test-complete
- RULE_SOURCE: brynhild.rules entry point
""".strip()


def get_rules_as_list():
    """
    Alternative: Get rules as a list of strings.

    This demonstrates that rules can be provided as multiple
    separate rule strings.
    """
    return [
        "# Rule 1\nThis is the first test rule.",
        "# Rule 2\nThis is the second test rule.",
    ]


def get_rules_as_dict():
    """
    Alternative: Get rules as a dict.

    This demonstrates that rules can be provided as a dict
    with a 'content' key.
    """
    return {
        "name": "test-rules-dict",
        "content": "# Dict Rules\nRules provided via dict format.",
    }


def get_rules_as_list_of_dicts():
    """
    Alternative: Get rules as a list of dicts.

    This demonstrates that rules can be provided as a list
    of dicts, each with 'content' and optional 'name'.
    """
    return [
        {"name": "rule-a", "content": "# Rule A\nFirst dict-style rule."},
        {"name": "rule-b", "content": "# Rule B\nSecond dict-style rule."},
    ]

