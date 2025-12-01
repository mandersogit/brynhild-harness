"""
Shared constants for Brynhild.

This module provides a single source of truth for default values
that are used across multiple modules.
"""

# LLM interaction defaults
DEFAULT_MAX_TOKENS = 8192
"""Default maximum tokens for LLM responses."""

DEFAULT_MAX_TOOL_ROUNDS = 20
"""Default maximum rounds of tool execution per conversation turn."""

# Tool execution defaults
DEFAULT_BASH_TIMEOUT_MS = 120_000
"""Default timeout for bash command execution (2 minutes)."""

# Truncation limits for display
DEFAULT_OUTPUT_TRUNCATE_LENGTH = 2000
"""Default length to truncate tool output for display."""

DEFAULT_INPUT_TRUNCATE_LENGTH = 200
"""Default length to truncate tool input values for display."""

