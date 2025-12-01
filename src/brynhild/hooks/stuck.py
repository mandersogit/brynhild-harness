"""
Stuck detection for conversation loops.

Detects when the agent is stuck in a loop (repeating the same tool calls
or encountering the same errors) and can inject a system message to help
the LLM self-correct.
"""

from __future__ import annotations

import dataclasses as _dataclasses
import hashlib as _hashlib
import json as _json
import typing as _typing

import brynhild.tools.base as tools_base


@_dataclasses.dataclass
class StuckState:
    """Result of stuck detection check."""

    is_stuck: bool
    """Whether the agent appears to be stuck."""

    reason: str | None = None
    """Human-readable explanation of why stuck was detected."""

    suggestion: str | None = None
    """Suggested system message to inject to help unstick."""


class StuckDetector:
    """
    Detects when the agent is stuck in a repetitive loop.

    Tracks recent tool calls and errors to identify patterns that suggest
    the agent is not making progress. When stuck is detected, provides
    a suggested system message to inject.

    Detection patterns:
    1. Same tool call repeated N times in a row
    2. Same error message repeated N times in a row
    3. No tool calls for N consecutive assistant messages (optional)
    """

    def __init__(
        self,
        *,
        repeat_threshold: int = 3,
        error_repeat_threshold: int = 3,
        no_progress_threshold: int = 5,
    ) -> None:
        """
        Initialize the stuck detector.

        Args:
            repeat_threshold: Number of identical tool calls to trigger stuck.
            error_repeat_threshold: Number of identical errors to trigger stuck.
            no_progress_threshold: Assistant messages without tool use to trigger.
        """
        self._repeat_threshold = repeat_threshold
        self._error_repeat_threshold = error_repeat_threshold
        self._no_progress_threshold = no_progress_threshold

        # History tracking
        self._recent_tool_calls: list[str] = []  # Hashes of tool calls
        self._recent_errors: list[str] = []  # Hashes of error messages
        self._messages_without_tool_use = 0

    def record_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, _typing.Any],
    ) -> None:
        """
        Record a tool call for stuck detection.

        Args:
            tool_name: Name of the tool called.
            tool_input: Input provided to the tool.
        """
        # Create a hash of the tool call for comparison
        call_hash = self._hash_tool_call(tool_name, tool_input)
        self._recent_tool_calls.append(call_hash)

        # Keep only recent history
        max_history = self._repeat_threshold * 2
        if len(self._recent_tool_calls) > max_history:
            self._recent_tool_calls = self._recent_tool_calls[-max_history:]

        # Reset no-progress counter
        self._messages_without_tool_use = 0

    def record_tool_result(
        self,
        tool_name: str,
        result: tools_base.ToolResult,
    ) -> None:
        """
        Record a tool result for stuck detection.

        Args:
            tool_name: Name of the tool.
            result: Result from tool execution.
        """
        if not result.success and result.error:
            error_hash = self._hash_error(tool_name, result.error)
            self._recent_errors.append(error_hash)

            # Keep only recent history
            max_history = self._error_repeat_threshold * 2
            if len(self._recent_errors) > max_history:
                self._recent_errors = self._recent_errors[-max_history:]

    def record_assistant_message(self, *, had_tool_use: bool) -> None:
        """
        Record an assistant message for no-progress detection.

        Args:
            had_tool_use: Whether the message included tool use.
        """
        if had_tool_use:
            self._messages_without_tool_use = 0
        else:
            self._messages_without_tool_use += 1

    def check(self) -> StuckState:
        """
        Check if the agent appears to be stuck.

        Returns:
            StuckState with detection result and suggestions.
        """
        # Check for repeated tool calls
        if self._check_repeated_calls():
            return StuckState(
                is_stuck=True,
                reason="Same tool call repeated multiple times",
                suggestion=self._get_repeated_call_suggestion(),
            )

        # Check for repeated errors
        if self._check_repeated_errors():
            return StuckState(
                is_stuck=True,
                reason="Same error encountered multiple times",
                suggestion=self._get_repeated_error_suggestion(),
            )

        # Check for no progress
        if self._check_no_progress():
            return StuckState(
                is_stuck=True,
                reason="No tool use for several messages",
                suggestion=self._get_no_progress_suggestion(),
            )

        return StuckState(is_stuck=False)

    def reset(self) -> None:
        """Reset all tracking state."""
        self._recent_tool_calls.clear()
        self._recent_errors.clear()
        self._messages_without_tool_use = 0

    def _hash_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, _typing.Any],
    ) -> str:
        """Create a hash of a tool call for comparison."""
        data = {"tool": tool_name, "input": tool_input}
        json_str = _json.dumps(data, sort_keys=True)
        return _hashlib.sha256(json_str.encode()).hexdigest()[:16]

    def _hash_error(self, tool_name: str, error: str) -> str:
        """Create a hash of an error for comparison."""
        data = {"tool": tool_name, "error": error}
        json_str = _json.dumps(data, sort_keys=True)
        return _hashlib.sha256(json_str.encode()).hexdigest()[:16]

    def _check_repeated_calls(self) -> bool:
        """Check if the last N tool calls are identical."""
        if len(self._recent_tool_calls) < self._repeat_threshold:
            return False

        recent = self._recent_tool_calls[-self._repeat_threshold :]
        return len(set(recent)) == 1

    def _check_repeated_errors(self) -> bool:
        """Check if the last N errors are identical."""
        if len(self._recent_errors) < self._error_repeat_threshold:
            return False

        recent = self._recent_errors[-self._error_repeat_threshold :]
        return len(set(recent)) == 1

    def _check_no_progress(self) -> bool:
        """Check if there's been no tool use for too long."""
        return self._messages_without_tool_use >= self._no_progress_threshold

    def _get_repeated_call_suggestion(self) -> str:
        """Get suggestion message for repeated tool calls."""
        return (
            "You appear to be repeating the same action. This approach isn't working. "
            "Please try a different approach or ask for clarification if you're unsure "
            "how to proceed."
        )

    def _get_repeated_error_suggestion(self) -> str:
        """Get suggestion message for repeated errors."""
        return (
            "You're encountering the same error repeatedly. Please analyze why this "
            "error is occurring and try a different approach. If the error persists, "
            "explain the issue and ask for guidance."
        )

    def _get_no_progress_suggestion(self) -> str:
        """Get suggestion message for no progress."""
        return (
            "You haven't used any tools for several messages. If you're ready to take "
            "action, please use the appropriate tools. If you need more information, "
            "please ask specific questions."
        )

