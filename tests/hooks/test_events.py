"""Tests for hook events, context, and result dataclasses."""

import json as _json
import pathlib as _pathlib

import brynhild.hooks.events as events
import brynhild.tools.base as tools_base


class TestHookEvent:
    """Tests for HookEvent enum."""

    def test_all_events_have_values(self) -> None:
        """Every event has a string value."""
        for event in events.HookEvent:
            assert isinstance(event.value, str)
            assert len(event.value) > 0

    def test_pre_tool_use_can_block(self) -> None:
        """PRE_TOOL_USE event can block operations."""
        assert events.HookEvent.PRE_TOOL_USE.can_block is True

    def test_post_tool_use_cannot_block(self) -> None:
        """POST_TOOL_USE event cannot block operations."""
        assert events.HookEvent.POST_TOOL_USE.can_block is False

    def test_session_events_cannot_block_or_modify(self) -> None:
        """Session events are informational only."""
        assert events.HookEvent.SESSION_START.can_block is False
        assert events.HookEvent.SESSION_START.can_modify is False
        assert events.HookEvent.SESSION_END.can_block is False
        assert events.HookEvent.SESSION_END.can_modify is False

    def test_error_event_cannot_block_or_modify(self) -> None:
        """Error event is informational only."""
        assert events.HookEvent.ERROR.can_block is False
        assert events.HookEvent.ERROR.can_modify is False

    def test_modifiable_events(self) -> None:
        """Check which events can modify data."""
        modifiable = {e for e in events.HookEvent if e.can_modify}
        assert events.HookEvent.PRE_TOOL_USE in modifiable
        assert events.HookEvent.POST_TOOL_USE in modifiable
        assert events.HookEvent.PRE_MESSAGE in modifiable
        assert events.HookEvent.SESSION_START not in modifiable


class TestHookAction:
    """Tests for HookAction enum."""

    def test_action_values(self) -> None:
        """Actions have expected string values."""
        assert events.HookAction.CONTINUE.value == "continue"
        assert events.HookAction.BLOCK.value == "block"
        assert events.HookAction.SKIP.value == "skip"


class TestHookContext:
    """Tests for HookContext dataclass."""

    def test_minimal_context(self) -> None:
        """Context can be created with minimal fields."""
        ctx = events.HookContext(
            event=events.HookEvent.SESSION_START,
            session_id="test-123",
            cwd=_pathlib.Path("/tmp"),
        )
        assert ctx.event == events.HookEvent.SESSION_START
        assert ctx.session_id == "test-123"
        assert ctx.cwd == _pathlib.Path("/tmp")
        assert ctx.tool is None
        assert ctx.tool_input is None

    def test_tool_context(self) -> None:
        """Context can include tool information."""
        ctx = events.HookContext(
            event=events.HookEvent.PRE_TOOL_USE,
            session_id="test-123",
            cwd=_pathlib.Path("/tmp"),
            tool="Bash",
            tool_input={"command": "ls -la"},
        )
        assert ctx.tool == "Bash"
        assert ctx.tool_input == {"command": "ls -la"}

    def test_to_dict_minimal(self) -> None:
        """to_dict includes only set fields."""
        ctx = events.HookContext(
            event=events.HookEvent.SESSION_START,
            session_id="test-123",
            cwd=_pathlib.Path("/tmp"),
        )
        d = ctx.to_dict()
        assert d["event"] == "session_start"
        assert d["session_id"] == "test-123"
        assert d["cwd"] == "/tmp"
        assert "tool" not in d
        assert "tool_input" not in d

    def test_to_dict_with_tool(self) -> None:
        """to_dict includes tool fields when set."""
        ctx = events.HookContext(
            event=events.HookEvent.PRE_TOOL_USE,
            session_id="test-123",
            cwd=_pathlib.Path("/tmp"),
            tool="Bash",
            tool_input={"command": "echo hello"},
        )
        d = ctx.to_dict()
        assert d["tool"] == "Bash"
        assert d["tool_input"] == {"command": "echo hello"}

    def test_to_dict_with_tool_result(self) -> None:
        """to_dict serializes tool result correctly."""
        result = tools_base.ToolResult(success=True, output="hello")
        ctx = events.HookContext(
            event=events.HookEvent.POST_TOOL_USE,
            session_id="test-123",
            cwd=_pathlib.Path("/tmp"),
            tool="Bash",
            tool_result=result,
        )
        d = ctx.to_dict()
        assert d["tool_result"]["success"] is True
        assert d["tool_result"]["output"] == "hello"

    def test_to_json(self) -> None:
        """to_json produces valid JSON."""
        ctx = events.HookContext(
            event=events.HookEvent.PRE_TOOL_USE,
            session_id="test-123",
            cwd=_pathlib.Path("/tmp"),
            tool="Bash",
            tool_input={"command": "ls"},
        )
        json_str = ctx.to_json()
        parsed = _json.loads(json_str)
        assert parsed["event"] == "pre_tool_use"
        assert parsed["tool"] == "Bash"

    def test_to_env_vars(self) -> None:
        """to_env_vars produces correct environment variables."""
        ctx = events.HookContext(
            event=events.HookEvent.PRE_TOOL_USE,
            session_id="test-123",
            cwd=_pathlib.Path("/tmp"),
            tool="Bash",
            tool_input={"command": "ls"},
        )
        env = ctx.to_env_vars()
        assert env["BRYNHILD_EVENT"] == "pre_tool_use"
        assert env["BRYNHILD_SESSION_ID"] == "test-123"
        assert env["BRYNHILD_CWD"] == "/tmp"
        assert env["BRYNHILD_TOOL_NAME"] == "Bash"
        assert _json.loads(env["BRYNHILD_TOOL_INPUT"]) == {"command": "ls"}

    def test_to_env_vars_with_result(self) -> None:
        """to_env_vars includes tool result variables."""
        result = tools_base.ToolResult(success=True, output="hello world")
        ctx = events.HookContext(
            event=events.HookEvent.POST_TOOL_USE,
            session_id="test-123",
            cwd=_pathlib.Path("/tmp"),
            tool="Bash",
            tool_result=result,
        )
        env = ctx.to_env_vars()
        assert env["BRYNHILD_TOOL_OUTPUT"] == "hello world"
        assert env["BRYNHILD_TOOL_SUCCESS"] == "true"


class TestHookResult:
    """Tests for HookResult dataclass."""

    def test_default_is_continue(self) -> None:
        """Default result is CONTINUE."""
        result = events.HookResult()
        assert result.action == events.HookAction.CONTINUE

    def test_continue_factory(self) -> None:
        """continue_() creates CONTINUE result."""
        result = events.HookResult.construct_continue()
        assert result.action == events.HookAction.CONTINUE
        assert result.message is None

    def test_block_factory(self) -> None:
        """block() creates BLOCK result with message."""
        result = events.HookResult.construct_block("Operation blocked")
        assert result.action == events.HookAction.BLOCK
        assert result.message == "Operation blocked"

    def test_skip_factory(self) -> None:
        """skip() creates SKIP result."""
        result = events.HookResult.construct_skip()
        assert result.action == events.HookAction.SKIP

    def test_from_dict_continue(self) -> None:
        """from_dict parses continue action."""
        result = events.HookResult.from_dict({"action": "continue"})
        assert result.action == events.HookAction.CONTINUE

    def test_from_dict_block_with_message(self) -> None:
        """from_dict parses block action with message."""
        result = events.HookResult.from_dict(
            {
                "action": "block",
                "message": "Blocked by hook",
            }
        )
        assert result.action == events.HookAction.BLOCK
        assert result.message == "Blocked by hook"

    def test_from_dict_with_modifications(self) -> None:
        """from_dict parses modifications."""
        result = events.HookResult.from_dict(
            {
                "action": "continue",
                "modified_input": {"command": "safe-command"},
            }
        )
        assert result.action == events.HookAction.CONTINUE
        assert result.modified_input == {"command": "safe-command"}

    def test_from_dict_unknown_action_defaults_continue(self) -> None:
        """from_dict defaults to CONTINUE for unknown action."""
        result = events.HookResult.from_dict({"action": "unknown"})
        assert result.action == events.HookAction.CONTINUE

    def test_to_dict(self) -> None:
        """to_dict serializes result correctly."""
        result = events.HookResult(
            action=events.HookAction.BLOCK,
            message="Blocked",
            modified_input={"key": "value"},
        )
        d = result.to_dict()
        assert d["action"] == "block"
        assert d["message"] == "Blocked"
        assert d["modified_input"] == {"key": "value"}

    def test_to_dict_minimal(self) -> None:
        """to_dict omits None fields."""
        result = events.HookResult.construct_continue()
        d = result.to_dict()
        assert d == {"action": "continue"}
