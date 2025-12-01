"""
Hook event types, context, and result dataclasses.

These define the core data structures for the hook system:
- HookEvent: Enum of all lifecycle events that can trigger hooks
- HookAction: What a hook wants to do (continue, block, skip)
- HookContext: Data passed to hooks about the current state
- HookResult: What a hook returns after execution
"""

from __future__ import annotations

import dataclasses as _dataclasses
import enum as _enum
import json as _json
import pathlib as _pathlib
import typing as _typing

import brynhild.tools.base as tools_base


class HookEvent(_enum.Enum):
    """
    Lifecycle events that can trigger hooks.

    Each event fires at a specific point in the agent lifecycle and provides
    relevant context to the hook.
    """

    # Session lifecycle
    SESSION_START = "session_start"
    """New session begins. Cannot block or modify."""

    SESSION_END = "session_end"
    """Session ends (normal or error). Cannot block or modify."""

    # Tool lifecycle
    PRE_TOOL_USE = "pre_tool_use"
    """Before a tool is executed. Can block and modify input."""

    POST_TOOL_USE = "post_tool_use"
    """After a tool completes. Can modify output."""

    # Message lifecycle
    PRE_MESSAGE = "pre_message"
    """Before sending user message to LLM. Can block and modify message."""

    POST_MESSAGE = "post_message"
    """After receiving LLM response. Can modify response."""

    # User input
    USER_PROMPT_SUBMIT = "user_prompt_submit"
    """User submits input. Can block and modify."""

    # Context management
    PRE_COMPACT = "pre_compact"
    """Before context window compaction. Can modify strategy."""

    # Error handling
    ERROR = "error"
    """When an error occurs. Cannot block or modify."""

    @property
    def can_block(self) -> bool:
        """Whether hooks for this event can block the operation."""
        return self in {
            HookEvent.PRE_TOOL_USE,
            HookEvent.PRE_MESSAGE,
            HookEvent.USER_PROMPT_SUBMIT,
        }

    @property
    def can_modify(self) -> bool:
        """Whether hooks for this event can modify data."""
        return self in {
            HookEvent.PRE_TOOL_USE,
            HookEvent.POST_TOOL_USE,
            HookEvent.PRE_MESSAGE,
            HookEvent.POST_MESSAGE,
            HookEvent.USER_PROMPT_SUBMIT,
            HookEvent.PRE_COMPACT,
        }


class HookAction(_enum.Enum):
    """
    Action a hook can request after execution.

    This determines how the agent proceeds after the hook runs.
    """

    CONTINUE = "continue"
    """Proceed normally (with optional modifications)."""

    BLOCK = "block"
    """Stop the operation and show message to user."""

    SKIP = "skip"
    """Skip silently (no error, no execution)."""


@_dataclasses.dataclass
class HookContext:
    """
    Context passed to hooks about the current state.

    Different events populate different fields. Fields not relevant to
    an event will be None.

    Attributes:
        event: The event that triggered this hook
        session_id: Current session identifier
        cwd: Current working directory
        tool: Tool name (for tool events)
        tool_input: Tool input dict (for pre_tool_use)
        tool_result: Tool result (for post_tool_use)
        message: User message (for message events)
        response: LLM response (for post_message)
        error: Exception info (for error event)
        compaction_strategy: Strategy name (for pre_compact)
    """

    event: HookEvent
    session_id: str
    cwd: _pathlib.Path

    # Tool events
    tool: str | None = None
    tool_input: dict[str, _typing.Any] | None = None
    tool_result: tools_base.ToolResult | None = None

    # Message events
    message: str | None = None
    response: str | None = None

    # Error event
    error: str | None = None
    error_type: str | None = None

    # Compaction event
    compaction_strategy: str | None = None

    def to_dict(self) -> dict[str, _typing.Any]:
        """Convert to JSON-serializable dict for script hooks."""
        result: dict[str, _typing.Any] = {
            "event": self.event.value,
            "session_id": self.session_id,
            "cwd": str(self.cwd),
        }

        if self.tool is not None:
            result["tool"] = self.tool
        if self.tool_input is not None:
            result["tool_input"] = self.tool_input
        if self.tool_result is not None:
            result["tool_result"] = self.tool_result.to_dict()
        if self.message is not None:
            result["message"] = self.message
        if self.response is not None:
            result["response"] = self.response
        if self.error is not None:
            result["error"] = self.error
        if self.error_type is not None:
            result["error_type"] = self.error_type
        if self.compaction_strategy is not None:
            result["compaction_strategy"] = self.compaction_strategy

        return result

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return _json.dumps(self.to_dict())

    def to_env_vars(self) -> dict[str, str]:
        """
        Convert to environment variables for command hooks.

        Returns a dict of BRYNHILD_* environment variables.
        """
        env: dict[str, str] = {
            "BRYNHILD_EVENT": self.event.value,
            "BRYNHILD_SESSION_ID": self.session_id,
            "BRYNHILD_CWD": str(self.cwd),
        }

        if self.tool is not None:
            env["BRYNHILD_TOOL_NAME"] = self.tool
        if self.tool_input is not None:
            env["BRYNHILD_TOOL_INPUT"] = _json.dumps(self.tool_input)
        if self.tool_result is not None:
            env["BRYNHILD_TOOL_OUTPUT"] = self.tool_result.output
            env["BRYNHILD_TOOL_SUCCESS"] = str(self.tool_result.success).lower()
        if self.message is not None:
            env["BRYNHILD_MESSAGE"] = self.message
        if self.response is not None:
            env["BRYNHILD_RESPONSE"] = self.response
        if self.error is not None:
            env["BRYNHILD_ERROR"] = self.error
        if self.error_type is not None:
            env["BRYNHILD_ERROR_TYPE"] = self.error_type

        return env


@_dataclasses.dataclass
class HookResult:
    """
    Result returned by a hook after execution.

    Attributes:
        action: What the hook wants to do (continue, block, skip)
        message: Optional message to show user (for block action)
        modified_input: Modified tool input (for pre_tool_use)
        modified_output: Modified tool output (for post_tool_use)
        modified_message: Modified user message (for pre_message)
        modified_response: Modified LLM response (for post_message)
        inject_system_message: System message to inject into conversation
    """

    action: HookAction = HookAction.CONTINUE
    message: str | None = None

    # Modifications (only one should be set based on event type)
    modified_input: dict[str, _typing.Any] | None = None
    modified_output: str | None = None
    modified_message: str | None = None
    modified_response: str | None = None

    # System message injection
    inject_system_message: str | None = None

    @classmethod
    def continue_(cls) -> HookResult:
        """Create a continue result (proceed normally)."""
        return cls(action=HookAction.CONTINUE)

    @classmethod
    def block(cls, message: str) -> HookResult:
        """Create a block result (stop operation with message)."""
        return cls(action=HookAction.BLOCK, message=message)

    @classmethod
    def skip(cls) -> HookResult:
        """Create a skip result (skip silently)."""
        return cls(action=HookAction.SKIP)

    @classmethod
    def from_dict(cls, data: dict[str, _typing.Any]) -> HookResult:
        """
        Parse a hook result from a JSON-parsed dict.

        This is used when parsing output from script hooks.
        """
        action_str = data.get("action", "continue")
        try:
            action = HookAction(action_str)
        except ValueError:
            action = HookAction.CONTINUE

        return cls(
            action=action,
            message=data.get("message"),
            modified_input=data.get("modified_input"),
            modified_output=data.get("modified_output"),
            modified_message=data.get("modified_message"),
            modified_response=data.get("modified_response"),
            inject_system_message=data.get("inject_system_message"),
        )

    def to_dict(self) -> dict[str, _typing.Any]:
        """Convert to JSON-serializable dict."""
        result: dict[str, _typing.Any] = {"action": self.action.value}

        if self.message is not None:
            result["message"] = self.message
        if self.modified_input is not None:
            result["modified_input"] = self.modified_input
        if self.modified_output is not None:
            result["modified_output"] = self.modified_output
        if self.modified_message is not None:
            result["modified_message"] = self.modified_message
        if self.modified_response is not None:
            result["modified_response"] = self.modified_response
        if self.inject_system_message is not None:
            result["inject_system_message"] = self.inject_system_message

        return result

