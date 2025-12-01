"""Tests for context compaction."""

import brynhild.hooks.compaction as compaction


class TestContextCompactor:
    """Tests for ContextCompactor class."""

    def test_no_compaction_when_under_threshold(self) -> None:
        """Don't compact when message count is under keep_recent."""
        compactor = compaction.ContextCompactor(keep_recent=10)

        messages = [
            {"role": "user", "content": f"Message {i}"}
            for i in range(5)
        ]

        result = compactor.compact(messages)
        assert result.compacted is False
        assert result.original_count == 5
        assert result.new_count == 5
        assert len(result.messages) == 5

    def test_compaction_when_over_threshold(self) -> None:
        """Compact when message count exceeds keep_recent."""
        compactor = compaction.ContextCompactor(keep_recent=5)

        messages = [
            {"role": "user", "content": f"Message {i}"}
            for i in range(20)
        ]

        result = compactor.compact(messages)
        assert result.compacted is True
        assert result.original_count == 20
        assert result.new_count == 5
        assert len(result.messages) == 5

    def test_keeps_most_recent_messages(self) -> None:
        """Compaction keeps the most recent messages."""
        compactor = compaction.ContextCompactor(keep_recent=3)

        messages = [
            {"role": "user", "content": f"Message {i}"}
            for i in range(10)
        ]

        result = compactor.compact(messages)

        # Should have messages 7, 8, 9 (the last 3)
        assert len(result.messages) == 3
        assert result.messages[0]["content"] == "Message 7"
        assert result.messages[1]["content"] == "Message 8"
        assert result.messages[2]["content"] == "Message 9"

    def test_preserves_system_messages(self) -> None:
        """System messages are preserved even when compacting."""
        compactor = compaction.ContextCompactor(keep_recent=2, keep_system=True)

        messages = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Message 0"},
            {"role": "assistant", "content": "Message 1"},
            {"role": "user", "content": "Message 2"},
            {"role": "assistant", "content": "Message 3"},
            {"role": "user", "content": "Message 4"},
        ]

        result = compactor.compact(messages)

        # Should have system message + last 2 non-system messages
        assert result.compacted is True
        assert len(result.messages) == 3
        assert result.messages[0]["role"] == "system"
        assert result.messages[1]["content"] == "Message 3"
        assert result.messages[2]["content"] == "Message 4"

    def test_can_disable_system_preservation(self) -> None:
        """Can disable preserving system messages."""
        compactor = compaction.ContextCompactor(keep_recent=2, keep_system=False)

        messages = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Message 0"},
            {"role": "assistant", "content": "Message 1"},
            {"role": "user", "content": "Message 2"},
        ]

        result = compactor.compact(messages)

        # Should have only the last 2 messages (no system)
        assert len(result.messages) == 2
        assert result.messages[0]["content"] == "Message 1"
        assert result.messages[1]["content"] == "Message 2"

    def test_compaction_result_has_summary(self) -> None:
        """Compaction result includes a summary of what was dropped."""
        compactor = compaction.ContextCompactor(keep_recent=2)

        messages = [{"role": "user", "content": f"M{i}"} for i in range(10)]

        result = compactor.compact(messages)
        assert result.summary is not None
        assert "8" in result.summary  # Dropped 8 messages

    def test_should_compact_token_threshold(self) -> None:
        """should_compact triggers at token threshold."""
        compactor = compaction.ContextCompactor(
            auto_threshold=0.8,
            max_tokens=1000,
        )

        messages = [{"role": "user", "content": "hi"}]

        # Below threshold
        assert compactor.should_compact(messages, current_tokens=700) is False

        # At/above threshold
        assert compactor.should_compact(messages, current_tokens=800) is True
        assert compactor.should_compact(messages, current_tokens=900) is True

    def test_should_compact_message_heuristic(self) -> None:
        """should_compact uses message count heuristic when tokens unknown."""
        compactor = compaction.ContextCompactor(
            auto_threshold=0.8,
            max_tokens=10000,  # 80% = 8000 tokens
        )

        # Few messages - should not trigger
        few_messages = [{"role": "user", "content": "hi"} for _ in range(5)]
        assert compactor.should_compact(few_messages) is False

        # Many messages - should trigger (heuristic: ~500 tokens per message)
        # 20 messages * 500 = 10000 estimated tokens > 8000 threshold
        many_messages = [{"role": "user", "content": "hi"} for _ in range(20)]
        assert compactor.should_compact(many_messages) is True

    def test_update_threshold(self) -> None:
        """Can update threshold settings."""
        compactor = compaction.ContextCompactor(
            auto_threshold=0.8,
            max_tokens=1000,
        )

        messages = [{"role": "user", "content": "hi"}]

        # Should not trigger at 700 tokens with 80% threshold
        assert compactor.should_compact(messages, current_tokens=700) is False

        # Update to 50% threshold
        compactor.update_threshold(auto_threshold=0.5)

        # Now should trigger at 700 tokens
        assert compactor.should_compact(messages, current_tokens=700) is True


class TestCompactMessagesFunction:
    """Tests for compact_messages convenience function."""

    def test_convenience_function_basic(self) -> None:
        """compact_messages function works correctly."""
        messages = [{"role": "user", "content": f"M{i}"} for i in range(10)]

        result = compaction.compact_messages(messages, keep_recent=3)

        assert result.compacted is True
        assert len(result.messages) == 3

    def test_convenience_function_no_op(self) -> None:
        """compact_messages is no-op for small lists."""
        messages = [{"role": "user", "content": "hi"}]

        result = compaction.compact_messages(messages, keep_recent=10)

        assert result.compacted is False
        assert len(result.messages) == 1

