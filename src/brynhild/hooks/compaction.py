"""
Context compaction for managing conversation length.

When the conversation context approaches the model's limit, compaction
reduces the message history while preserving important information.

Strategies:
- recent_messages: Keep only the most recent N messages
- (future) summary: LLM-generated summary of older messages
"""

from __future__ import annotations

import dataclasses as _dataclasses
import typing as _typing


@_dataclasses.dataclass
class CompactionResult:
    """Result of context compaction."""

    compacted: bool
    """Whether compaction was performed."""

    original_count: int
    """Number of messages before compaction."""

    new_count: int
    """Number of messages after compaction."""

    messages: list[dict[str, _typing.Any]]
    """The compacted message list."""

    summary: str | None = None
    """Summary of removed messages (if applicable)."""


class ContextCompactor:
    """
    Compacts conversation context to stay within limits.

    Uses a simple "keep recent messages" strategy. Future versions
    could add LLM-based summarization.
    """

    def __init__(
        self,
        *,
        keep_recent: int = 20,
        keep_system: bool = True,
        auto_threshold: float = 0.8,
        max_tokens: int = 100000,
    ) -> None:
        """
        Initialize the compactor.

        Args:
            keep_recent: Number of recent messages to keep.
            keep_system: Whether to always keep system messages.
            auto_threshold: Token usage ratio to trigger auto-compaction (0.8 = 80%).
            max_tokens: Maximum context tokens (for threshold calculation).
        """
        self._keep_recent = keep_recent
        self._keep_system = keep_system
        self._auto_threshold = auto_threshold
        self._max_tokens = max_tokens

    def should_compact(
        self,
        messages: list[dict[str, _typing.Any]],
        current_tokens: int | None = None,
    ) -> bool:
        """
        Check if compaction should be triggered.

        Args:
            messages: Current message list.
            current_tokens: Current token count (if known).

        Returns:
            True if compaction should be triggered.
        """
        # Token-based threshold
        if current_tokens is not None:
            threshold_tokens = int(self._max_tokens * self._auto_threshold)
            if current_tokens >= threshold_tokens:
                return True

        # Message count heuristic (rough estimate if tokens unknown)
        # Assume ~500 tokens per message average
        if current_tokens is None:
            estimated_tokens = len(messages) * 500
            threshold_tokens = int(self._max_tokens * self._auto_threshold)
            if estimated_tokens >= threshold_tokens:
                return True

        return False

    def compact(
        self,
        messages: list[dict[str, _typing.Any]],
    ) -> CompactionResult:
        """
        Compact the message history.

        Keeps the most recent messages plus any system messages
        if configured.

        Args:
            messages: The message list to compact.

        Returns:
            CompactionResult with compacted messages.
        """
        original_count = len(messages)

        if original_count <= self._keep_recent:
            # Nothing to compact
            return CompactionResult(
                compacted=False,
                original_count=original_count,
                new_count=original_count,
                messages=messages,
            )

        # Separate system messages if we're keeping them
        system_messages: list[dict[str, _typing.Any]] = []
        non_system_messages: list[dict[str, _typing.Any]] = []

        for msg in messages:
            if self._keep_system and msg.get("role") == "system":
                system_messages.append(msg)
            else:
                non_system_messages.append(msg)

        # Keep recent non-system messages
        recent_messages = non_system_messages[-self._keep_recent :]

        # Combine system + recent
        compacted = system_messages + recent_messages

        # Calculate how many were dropped
        dropped_count = original_count - len(compacted)

        return CompactionResult(
            compacted=True,
            original_count=original_count,
            new_count=len(compacted),
            messages=compacted,
            summary=f"Dropped {dropped_count} older messages to fit context window.",
        )

    def update_threshold(
        self,
        *,
        auto_threshold: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        """
        Update compaction thresholds.

        Args:
            auto_threshold: New auto-compaction threshold (0.0-1.0).
            max_tokens: New max tokens value.
        """
        if auto_threshold is not None:
            self._auto_threshold = auto_threshold
        if max_tokens is not None:
            self._max_tokens = max_tokens


# Convenience function for simple compaction
def compact_messages(
    messages: list[dict[str, _typing.Any]],
    *,
    keep_recent: int = 20,
) -> CompactionResult:
    """
    Compact a message list, keeping recent messages.

    Args:
        messages: Messages to compact.
        keep_recent: Number of recent messages to keep.

    Returns:
        CompactionResult with compacted messages.
    """
    compactor = ContextCompactor(keep_recent=keep_recent)
    return compactor.compact(messages)

