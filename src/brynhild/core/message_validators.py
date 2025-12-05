"""Message structure validators for conversation integrity.

This module provides validators that ensure messages sent to LLMs follow
correct structural invariants. These validators should be used:
1. In tests to catch message construction bugs
2. Optionally at runtime to fail-fast on invariant violations

The validators check for issues like:
- Message ordering violations (feedback before response)
- Turn-taking violations (two user messages in a row)
- Tool call ID mismatches (orphan tool calls or results)
- Missing required fields
"""

import typing as _typing


class MessageValidationError(Exception):
    """Raised when message structure invariants are violated."""

    def __init__(
        self,
        message: str,
        *,
        violation_type: str,
        messages: list[dict[str, _typing.Any]] | None = None,
        context: dict[str, _typing.Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.violation_type = violation_type
        self.messages = messages
        self.context = context or {}


def validate_message_structure(
    messages: list[dict[str, _typing.Any]],
    *,
    strict: bool = True,
) -> list[str]:
    """Validate all message structure invariants.

    Args:
        messages: List of messages to validate.
        strict: If True, raise MessageValidationError on first violation.
                If False, collect and return all violations as strings.

    Returns:
        List of violation descriptions (empty if valid).

    Raises:
        MessageValidationError: If strict=True and any violation found.
    """
    violations: list[str] = []

    # Run all validators
    validators = [
        _validate_required_fields,
        _validate_turn_taking,
        _validate_tool_call_consistency,
        _validate_system_message_position,
        _validate_no_empty_content,
        _validate_feedback_ordering,
    ]

    for validator in validators:
        try:
            validator(messages)
        except MessageValidationError as e:
            if strict:
                raise
            violations.append(f"[{e.violation_type}] {e}")

    return violations


def _validate_required_fields(messages: list[dict[str, _typing.Any]]) -> None:
    """Validate all messages have required fields."""
    for i, msg in enumerate(messages):
        role = msg.get("role")
        if not role:
            raise MessageValidationError(
                f"Message {i} missing 'role' field",
                violation_type="missing_role",
                messages=messages,
                context={"index": i, "message": msg},
            )

        if role not in ("system", "user", "assistant", "tool", "tool_result"):
            raise MessageValidationError(
                f"Message {i} has invalid role: {role!r}",
                violation_type="invalid_role",
                messages=messages,
                context={"index": i, "role": role},
            )

        # Assistant messages need content OR tool_calls
        if role == "assistant":
            has_content = bool(msg.get("content"))
            has_tool_calls = bool(msg.get("tool_calls"))
            if not has_content and not has_tool_calls:
                raise MessageValidationError(
                    f"Assistant message {i} has neither content nor tool_calls",
                    violation_type="empty_assistant",
                    messages=messages,
                    context={"index": i, "message": msg},
                )

        # Tool results need tool_call_id
        if role in ("tool", "tool_result") and not msg.get("tool_call_id"):
            raise MessageValidationError(
                f"Tool result message {i} missing 'tool_call_id'",
                violation_type="missing_tool_call_id",
                messages=messages,
                context={"index": i, "message": msg},
            )


def _validate_turn_taking(messages: list[dict[str, _typing.Any]]) -> None:
    """Validate messages follow expected turn-taking patterns.

    Rules:
    - No two user messages in a row (almost always a bug)
    - No two assistant messages in a row without tool results between
    """
    prev_role: str | None = None
    prev_had_tool_calls = False

    for i, msg in enumerate(messages):
        role = msg.get("role", "")

        # Two user messages in a row is almost always wrong
        if role == "user" and prev_role == "user":
            raise MessageValidationError(
                f"Two user messages in a row at index {i-1} and {i}",
                violation_type="consecutive_user_messages",
                messages=messages,
                context={"indices": [i - 1, i]},
            )

        # Two assistant messages in a row without tool results is suspicious
        # (unless the first had tool_calls and we're now seeing tool results)
        if role == "assistant" and prev_role == "assistant":
            raise MessageValidationError(
                f"Two assistant messages in a row at index {i-1} and {i}",
                violation_type="consecutive_assistant_messages",
                messages=messages,
                context={"indices": [i - 1, i]},
            )

        # After assistant with tool_calls, next should be tool result(s)
        if prev_had_tool_calls and role not in ("tool", "tool_result"):
            raise MessageValidationError(
                f"Expected tool result after assistant tool_calls at {i-1}, got {role} at {i}",
                violation_type="missing_tool_result",
                messages=messages,
                context={"indices": [i - 1, i], "expected": "tool/tool_result", "got": role},
            )

        prev_role = role
        prev_had_tool_calls = bool(msg.get("tool_calls"))


def _validate_tool_call_consistency(messages: list[dict[str, _typing.Any]]) -> None:
    """Validate tool_call_ids are consistent between calls and results.

    Rules:
    - Every tool result must reference a tool_call_id from a preceding assistant message
    - Every tool_call should have a corresponding result (warning, not error)
    """
    # Track pending tool_call_ids that need results
    pending_tool_calls: dict[str, int] = {}  # id -> message index

    for i, msg in enumerate(messages):
        role = msg.get("role", "")

        # Assistant with tool_calls - register the IDs
        if role == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                tc_id = tc.get("id")
                if tc_id:
                    pending_tool_calls[tc_id] = i

        # Tool result - verify the ID exists
        if role in ("tool", "tool_result"):
            tc_id = msg.get("tool_call_id")
            if tc_id and tc_id not in pending_tool_calls:
                # Check if it's a synthetic ID (from thinking-only recovery)
                if not tc_id.startswith("thinking-only-"):
                    raise MessageValidationError(
                        f"Tool result at {i} has orphan tool_call_id: {tc_id!r}",
                        violation_type="orphan_tool_result",
                        messages=messages,
                        context={"index": i, "tool_call_id": tc_id},
                    )
            elif tc_id:
                # Mark as resolved
                del pending_tool_calls[tc_id]

    # Note: We don't error on unresolved tool_calls because the conversation
    # might be in progress. Tests can check this explicitly if needed.


def _validate_system_message_position(messages: list[dict[str, _typing.Any]]) -> None:
    """Validate system message is first (if present)."""
    system_indices = [i for i, m in enumerate(messages) if m.get("role") == "system"]

    if system_indices and system_indices[0] != 0:
        raise MessageValidationError(
            f"System message at index {system_indices[0]}, expected at 0",
            violation_type="misplaced_system_message",
            messages=messages,
            context={"index": system_indices[0]},
        )

    if len(system_indices) > 1:
        raise MessageValidationError(
            f"Multiple system messages at indices {system_indices}",
            violation_type="multiple_system_messages",
            messages=messages,
            context={"indices": system_indices},
        )


def _validate_no_empty_content(messages: list[dict[str, _typing.Any]]) -> None:
    """Validate messages don't have empty content where content is expected."""
    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = msg.get("content")

        # User and system messages should have content
        if role in ("user", "system"):  # noqa: SIM102
            if content is None or (isinstance(content, str) and not content.strip()):
                raise MessageValidationError(
                    f"{role.capitalize()} message {i} has empty content",
                    violation_type="empty_content",
                    messages=messages,
                    context={"index": i, "role": role},
                )

        # Tool results should have content
        if role in ("tool", "tool_result"):  # noqa: SIM102
            if content is None or (isinstance(content, str) and not content.strip()):
                raise MessageValidationError(
                    f"Tool result {i} has empty content",
                    violation_type="empty_tool_result",
                    messages=messages,
                    context={"index": i},
                )


def _validate_feedback_ordering(messages: list[dict[str, _typing.Any]]) -> None:
    """Validate feedback messages come after what they respond to.

    Detects patterns like user feedback appearing before the assistant
    response it's critiquing.
    """
    # Known feedback patterns
    feedback_patterns = [
        "did not call the Finish tool",
        "Your response contained only thinking",
        "incomplete_response",
    ]

    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = str(msg.get("content", ""))

        # Check if this is a feedback message
        is_feedback = any(pattern in content for pattern in feedback_patterns)

        if is_feedback and role == "user":
            # Feedback from user should have an assistant message before it
            # (the thing being critiqued)
            if i == 0:
                raise MessageValidationError(
                    f"Feedback message at {i} has nothing before it",
                    violation_type="feedback_without_predecessor",
                    messages=messages,
                    context={"index": i},
                )

            prev_msg = messages[i - 1]
            if prev_msg.get("role") != "assistant":
                raise MessageValidationError(
                    f"Feedback message at {i} should follow assistant message, "
                    f"but follows {prev_msg.get('role')!r}",
                    violation_type="feedback_ordering",
                    messages=messages,
                    context={"index": i, "prev_role": prev_msg.get("role")},
                )


def validate_tool_call_result_pairs(
    messages: list[dict[str, _typing.Any]],
) -> dict[str, _typing.Any]:
    """Validate and return statistics about tool call/result pairing.

    Returns:
        Dict with:
        - total_tool_calls: Number of tool calls made
        - total_tool_results: Number of tool results
        - matched_pairs: Number of correctly matched pairs
        - orphan_calls: List of tool_call_ids with no result
        - orphan_results: List of tool_call_ids with no matching call
    """
    tool_calls: dict[str, dict[str, _typing.Any]] = {}  # id -> call info
    tool_results: dict[str, dict[str, _typing.Any]] = {}  # id -> result info

    for i, msg in enumerate(messages):
        role = msg.get("role", "")

        if role == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                tc_id = tc.get("id", f"unknown-{i}")
                tool_calls[tc_id] = {"index": i, "call": tc}

        if role in ("tool", "tool_result"):
            tc_id = msg.get("tool_call_id", f"unknown-{i}")
            tool_results[tc_id] = {"index": i, "content": msg.get("content")}

    call_ids = set(tool_calls.keys())
    result_ids = set(tool_results.keys())

    return {
        "total_tool_calls": len(tool_calls),
        "total_tool_results": len(tool_results),
        "matched_pairs": len(call_ids & result_ids),
        "orphan_calls": list(call_ids - result_ids),
        "orphan_results": list(result_ids - call_ids),
    }


def assert_valid_messages(
    messages: list[dict[str, _typing.Any]],
    *,
    context: str = "",
) -> None:
    """Assert that messages pass all validation checks.

    Use this in tests to validate message structure.

    Args:
        messages: Messages to validate.
        context: Optional context string for error messages.

    Raises:
        AssertionError: If any validation fails.
    """
    try:
        validate_message_structure(messages, strict=True)
    except MessageValidationError as e:
        ctx = f" ({context})" if context else ""
        raise AssertionError(
            f"Message validation failed{ctx}: [{e.violation_type}] {e}\n"
            f"Messages: {_format_messages_for_error(messages)}"
        ) from e


def _format_messages_for_error(messages: list[dict[str, _typing.Any]]) -> str:
    """Format messages for readable error output."""
    lines = []
    for i, msg in enumerate(messages):
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if isinstance(content, str) and len(content) > 100:
            content = content[:100] + "..."
        tool_calls = msg.get("tool_calls")
        tc_str = f" [tool_calls: {len(tool_calls)}]" if tool_calls else ""
        tc_id = msg.get("tool_call_id", "")
        tc_id_str = f" [tool_call_id: {tc_id}]" if tc_id else ""
        lines.append(f"  [{i}] {role}{tc_str}{tc_id_str}: {content!r}")
    return "\n".join(lines)

