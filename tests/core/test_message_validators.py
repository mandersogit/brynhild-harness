"""Tests for message structure validators.

These tests ensure our validators correctly catch message construction bugs.
"""

import pytest as _pytest

import brynhild.core.message_validators as validators


class TestRequiredFields:
    """Tests for required field validation."""

    def test_missing_role_raises(self) -> None:
        """Messages without role should fail."""
        messages = [{"content": "Hello"}]
        with _pytest.raises(validators.MessageValidationError) as exc_info:
            validators.validate_message_structure(messages)
        assert exc_info.value.violation_type == "missing_role"

    def test_invalid_role_raises(self) -> None:
        """Messages with invalid role should fail."""
        messages = [{"role": "bot", "content": "Hello"}]
        with _pytest.raises(validators.MessageValidationError) as exc_info:
            validators.validate_message_structure(messages)
        assert exc_info.value.violation_type == "invalid_role"

    def test_valid_roles_pass(self) -> None:
        """All valid roles should pass."""
        valid_roles = ["system", "user", "assistant", "tool", "tool_result"]
        for role in valid_roles:
            if role in ("tool", "tool_result"):
                messages = [
                    {"role": "user", "content": "Hi"},
                    {"role": "assistant", "tool_calls": [{"id": "tc1", "type": "function", "function": {"name": "test", "arguments": "{}"}}]},
                    {"role": role, "tool_call_id": "tc1", "content": "result"},
                ]
            elif role == "system":
                messages = [{"role": role, "content": "System prompt"}]
            elif role == "assistant":
                messages = [
                    {"role": "user", "content": "Hi"},
                    {"role": role, "content": "Hello"},
                ]
            else:
                messages = [{"role": role, "content": "Test"}]
            # Should not raise
            validators.validate_message_structure(messages)

    def test_assistant_needs_content_or_tool_calls(self) -> None:
        """Assistant messages must have content or tool_calls."""
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant"},  # Empty - should fail
        ]
        with _pytest.raises(validators.MessageValidationError) as exc_info:
            validators.validate_message_structure(messages)
        assert exc_info.value.violation_type == "empty_assistant"

    def test_assistant_with_only_tool_calls_passes(self) -> None:
        """Assistant with tool_calls but no content should pass."""
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "tool_calls": [{"id": "tc1", "type": "function", "function": {"name": "test", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "tc1", "content": "result"},
        ]
        # Should not raise
        validators.validate_message_structure(messages)

    def test_tool_result_needs_tool_call_id(self) -> None:
        """Tool result messages must have tool_call_id."""
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "tool_calls": [{"id": "tc1", "type": "function", "function": {"name": "test", "arguments": "{}"}}]},
            {"role": "tool", "content": "result"},  # Missing tool_call_id
        ]
        with _pytest.raises(validators.MessageValidationError) as exc_info:
            validators.validate_message_structure(messages)
        assert exc_info.value.violation_type == "missing_tool_call_id"


class TestTurnTaking:
    """Tests for turn-taking validation."""

    def test_two_user_messages_in_row_raises(self) -> None:
        """Two consecutive user messages should fail."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "user", "content": "Are you there?"},  # Consecutive user
        ]
        with _pytest.raises(validators.MessageValidationError) as exc_info:
            validators.validate_message_structure(messages)
        assert exc_info.value.violation_type == "consecutive_user_messages"

    def test_two_assistant_messages_in_row_raises(self) -> None:
        """Two consecutive assistant messages should fail."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
            {"role": "assistant", "content": "How can I help?"},  # Consecutive assistant
        ]
        with _pytest.raises(validators.MessageValidationError) as exc_info:
            validators.validate_message_structure(messages)
        assert exc_info.value.violation_type == "consecutive_assistant_messages"

    def test_user_assistant_user_assistant_passes(self) -> None:
        """Normal alternation should pass."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
            {"role": "user", "content": "How are you?"},
            {"role": "assistant", "content": "I'm good!"},
        ]
        validators.validate_message_structure(messages)

    def test_tool_results_between_assistant_and_user_passes(self) -> None:
        """Tool results between assistant and user should pass."""
        messages = [
            {"role": "user", "content": "What's the weather?"},
            {"role": "assistant", "tool_calls": [{"id": "tc1", "type": "function", "function": {"name": "weather", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "tc1", "content": "Sunny, 72F"},
            {"role": "assistant", "content": "It's sunny and 72 degrees!"},
        ]
        validators.validate_message_structure(messages)

    def test_missing_tool_result_after_tool_calls_raises(self) -> None:
        """After assistant tool_calls, next must be tool result."""
        messages = [
            {"role": "user", "content": "What's the weather?"},
            {"role": "assistant", "tool_calls": [{"id": "tc1", "type": "function", "function": {"name": "weather", "arguments": "{}"}}]},
            {"role": "user", "content": "Never mind"},  # Should be tool result first
        ]
        with _pytest.raises(validators.MessageValidationError) as exc_info:
            validators.validate_message_structure(messages)
        assert exc_info.value.violation_type == "missing_tool_result"


class TestToolCallConsistency:
    """Tests for tool_call_id consistency validation."""

    def test_orphan_tool_result_raises(self) -> None:
        """Tool result with unknown ID should fail."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "tool_calls": [{"id": "tc1", "type": "function", "function": {"name": "test", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "tc2", "content": "result"},  # tc2 doesn't exist
        ]
        with _pytest.raises(validators.MessageValidationError) as exc_info:
            validators.validate_message_structure(messages)
        assert exc_info.value.violation_type == "orphan_tool_result"

    def test_matching_tool_call_ids_passes(self) -> None:
        """Matching tool_call_ids should pass."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "tool_calls": [
                {"id": "tc1", "type": "function", "function": {"name": "test1", "arguments": "{}"}},
                {"id": "tc2", "type": "function", "function": {"name": "test2", "arguments": "{}"}},
            ]},
            {"role": "tool", "tool_call_id": "tc1", "content": "result1"},
            {"role": "tool", "tool_call_id": "tc2", "content": "result2"},
        ]
        validators.validate_message_structure(messages)

    def test_thinking_only_synthetic_id_passes(self) -> None:
        """Synthetic thinking-only IDs should be allowed."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "tool_calls": [{"id": "thinking-only-abc123", "type": "function", "function": {"name": "incomplete_response", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "thinking-only-abc123", "content": "ERROR: thinking only"},
        ]
        validators.validate_message_structure(messages)


class TestSystemMessage:
    """Tests for system message position validation."""

    def test_system_must_be_first(self) -> None:
        """System message must be at index 0."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "system", "content": "You are helpful"},  # Wrong position
        ]
        with _pytest.raises(validators.MessageValidationError) as exc_info:
            validators.validate_message_structure(messages)
        assert exc_info.value.violation_type == "misplaced_system_message"

    def test_system_at_start_passes(self) -> None:
        """System message at start should pass."""
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        validators.validate_message_structure(messages)

    def test_multiple_system_messages_raises(self) -> None:
        """Multiple system messages should fail."""
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "system", "content": "Be concise"},  # Second system
        ]
        with _pytest.raises(validators.MessageValidationError) as exc_info:
            validators.validate_message_structure(messages)
        assert exc_info.value.violation_type == "multiple_system_messages"


class TestEmptyContent:
    """Tests for empty content validation."""

    def test_empty_user_content_raises(self) -> None:
        """User messages with empty content should fail."""
        messages = [{"role": "user", "content": ""}]
        with _pytest.raises(validators.MessageValidationError) as exc_info:
            validators.validate_message_structure(messages)
        assert exc_info.value.violation_type == "empty_content"

    def test_whitespace_only_user_content_raises(self) -> None:
        """User messages with whitespace-only content should fail."""
        messages = [{"role": "user", "content": "   \n\t  "}]
        with _pytest.raises(validators.MessageValidationError) as exc_info:
            validators.validate_message_structure(messages)
        assert exc_info.value.violation_type == "empty_content"

    def test_empty_system_content_raises(self) -> None:
        """System messages with empty content should fail."""
        messages = [{"role": "system", "content": ""}]
        with _pytest.raises(validators.MessageValidationError) as exc_info:
            validators.validate_message_structure(messages)
        assert exc_info.value.violation_type == "empty_content"

    def test_empty_tool_result_raises(self) -> None:
        """Tool results with empty content should fail."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "tool_calls": [{"id": "tc1", "type": "function", "function": {"name": "test", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "tc1", "content": ""},  # Empty result
        ]
        with _pytest.raises(validators.MessageValidationError) as exc_info:
            validators.validate_message_structure(messages)
        assert exc_info.value.violation_type == "empty_tool_result"


class TestFeedbackOrdering:
    """Tests for feedback message ordering validation."""

    def test_feedback_without_predecessor_raises(self) -> None:
        """Feedback as first message should fail."""
        messages = [
            {"role": "user", "content": "You did not call the Finish tool. Please do so."},
        ]
        with _pytest.raises(validators.MessageValidationError) as exc_info:
            validators.validate_message_structure(messages)
        assert exc_info.value.violation_type == "feedback_without_predecessor"

    def test_feedback_after_user_raises(self) -> None:
        """Feedback after user message (not assistant) should fail."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "user", "content": "You did not call the Finish tool."},  # Should follow assistant
        ]
        with _pytest.raises(validators.MessageValidationError) as exc_info:
            validators.validate_message_structure(messages)
        # Will hit consecutive_user_messages first, then feedback_ordering
        assert exc_info.value.violation_type in ("consecutive_user_messages", "feedback_ordering")

    def test_feedback_after_assistant_passes(self) -> None:
        """Feedback after assistant message should pass."""
        messages = [
            {"role": "user", "content": "Do something"},
            {"role": "assistant", "content": "I did something"},
            {"role": "user", "content": "You did not call the Finish tool. Please call Finish now."},
        ]
        validators.validate_message_structure(messages)

    def test_thinking_only_feedback_ordering(self) -> None:
        """Thinking-only feedback should follow assistant."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "tool_calls": [{"id": "thinking-only-abc", "type": "function", "function": {"name": "incomplete_response", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "thinking-only-abc", "content": "ERROR: Your response contained only thinking"},
        ]
        validators.validate_message_structure(messages)


class TestToolCallResultPairs:
    """Tests for tool call/result pairing statistics."""

    def test_empty_messages(self) -> None:
        """Empty messages should have zero counts."""
        result = validators.validate_tool_call_result_pairs([])
        assert result["total_tool_calls"] == 0
        assert result["total_tool_results"] == 0
        assert result["matched_pairs"] == 0

    def test_matched_pairs(self) -> None:
        """Properly matched pairs should be counted."""
        messages = [
            {"role": "assistant", "tool_calls": [
                {"id": "tc1", "type": "function", "function": {"name": "a", "arguments": "{}"}},
                {"id": "tc2", "type": "function", "function": {"name": "b", "arguments": "{}"}},
            ]},
            {"role": "tool", "tool_call_id": "tc1", "content": "r1"},
            {"role": "tool", "tool_call_id": "tc2", "content": "r2"},
        ]
        result = validators.validate_tool_call_result_pairs(messages)
        assert result["total_tool_calls"] == 2
        assert result["total_tool_results"] == 2
        assert result["matched_pairs"] == 2
        assert result["orphan_calls"] == []
        assert result["orphan_results"] == []

    def test_orphan_call(self) -> None:
        """Unresolved tool calls should be reported."""
        messages = [
            {"role": "assistant", "tool_calls": [
                {"id": "tc1", "type": "function", "function": {"name": "a", "arguments": "{}"}},
                {"id": "tc2", "type": "function", "function": {"name": "b", "arguments": "{}"}},
            ]},
            {"role": "tool", "tool_call_id": "tc1", "content": "r1"},
            # tc2 has no result
        ]
        result = validators.validate_tool_call_result_pairs(messages)
        assert result["total_tool_calls"] == 2
        assert result["total_tool_results"] == 1
        assert result["matched_pairs"] == 1
        assert "tc2" in result["orphan_calls"]


class TestAssertValidMessages:
    """Tests for the assertion helper."""

    def test_valid_messages_pass(self) -> None:
        """Valid messages should not raise."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        validators.assert_valid_messages(messages)

    def test_invalid_messages_raise_assertion_error(self) -> None:
        """Invalid messages should raise AssertionError."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "user", "content": "Hello again"},  # Consecutive user
        ]
        with _pytest.raises(AssertionError) as exc_info:
            validators.assert_valid_messages(messages, context="test context")
        assert "consecutive_user_messages" in str(exc_info.value)
        assert "test context" in str(exc_info.value)


class TestNonStrictMode:
    """Tests for non-strict validation mode."""

    def test_non_strict_collects_all_violations(self) -> None:
        """Non-strict mode should collect all violations."""
        messages = [
            {"role": "user", "content": ""},  # Empty content
            {"role": "user", "content": "Hello"},  # Consecutive user
        ]
        violations = validators.validate_message_structure(messages, strict=False)
        # Should have at least two violations
        assert len(violations) >= 2
        assert any("empty_content" in v for v in violations)
        assert any("consecutive_user_messages" in v for v in violations)

