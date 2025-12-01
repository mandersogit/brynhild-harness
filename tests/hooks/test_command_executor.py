"""Tests for command hook executor."""

import pathlib as _pathlib

import pytest as _pytest

import brynhild.hooks.config as config
import brynhild.hooks.events as events
import brynhild.hooks.executors.command as command_executor


class TestCommandHookExecutor:
    """Tests for CommandHookExecutor."""

    @_pytest.fixture
    def executor(self, tmp_path: _pathlib.Path) -> command_executor.CommandHookExecutor:
        """Create executor with tmp_path as project root."""
        return command_executor.CommandHookExecutor(project_root=tmp_path)

    @_pytest.fixture
    def context(self, tmp_path: _pathlib.Path) -> events.HookContext:
        """Create a basic hook context."""
        return events.HookContext(
            event=events.HookEvent.PRE_TOOL_USE,
            session_id="test-session",
            cwd=tmp_path,
            tool="Bash",
            tool_input={"command": "ls -la"},
        )

    @_pytest.mark.asyncio
    async def test_exit_zero_returns_continue(
        self,
        executor: command_executor.CommandHookExecutor,
        context: events.HookContext,
    ) -> None:
        """Command with exit 0 returns CONTINUE."""
        hook_def = config.HookDefinition(
            name="test-hook",
            type="command",
            command="exit 0",
        )

        result = await executor.execute(hook_def, context)
        assert result.action == events.HookAction.CONTINUE

    @_pytest.mark.asyncio
    async def test_exit_nonzero_returns_block(
        self,
        executor: command_executor.CommandHookExecutor,
        context: events.HookContext,
    ) -> None:
        """Command with non-zero exit returns BLOCK."""
        hook_def = config.HookDefinition(
            name="test-hook",
            type="command",
            command="exit 1",
        )

        result = await executor.execute(hook_def, context)
        assert result.action == events.HookAction.BLOCK

    @_pytest.mark.asyncio
    async def test_custom_block_message(
        self,
        executor: command_executor.CommandHookExecutor,
        context: events.HookContext,
    ) -> None:
        """Hook's message field is used for block message."""
        hook_def = config.HookDefinition(
            name="test-hook",
            type="command",
            command="exit 1",
            message="Custom block message",
        )

        result = await executor.execute(hook_def, context)
        assert result.action == events.HookAction.BLOCK
        assert result.message == "Custom block message"

    @_pytest.mark.asyncio
    async def test_stderr_used_as_block_message(
        self,
        executor: command_executor.CommandHookExecutor,
        context: events.HookContext,
    ) -> None:
        """stderr output is used as block message when no message configured."""
        hook_def = config.HookDefinition(
            name="test-hook",
            type="command",
            command="echo 'error message' >&2; exit 1",
        )

        result = await executor.execute(hook_def, context)
        assert result.action == events.HookAction.BLOCK
        assert "error message" in result.message  # type: ignore[operator]

    @_pytest.mark.asyncio
    async def test_env_vars_injected(
        self,
        executor: command_executor.CommandHookExecutor,
        context: events.HookContext,
    ) -> None:
        """Context is available via environment variables."""
        hook_def = config.HookDefinition(
            name="test-hook",
            type="command",
            command='test "$BRYNHILD_TOOL_NAME" = "Bash"',
        )

        result = await executor.execute(hook_def, context)
        assert result.action == events.HookAction.CONTINUE

    @_pytest.mark.asyncio
    async def test_env_var_event(
        self,
        executor: command_executor.CommandHookExecutor,
        context: events.HookContext,
    ) -> None:
        """BRYNHILD_EVENT is set correctly."""
        hook_def = config.HookDefinition(
            name="test-hook",
            type="command",
            command='test "$BRYNHILD_EVENT" = "pre_tool_use"',
        )

        result = await executor.execute(hook_def, context)
        assert result.action == events.HookAction.CONTINUE

    @_pytest.mark.asyncio
    async def test_timeout_triggers_block(
        self,
        executor: command_executor.CommandHookExecutor,
        context: events.HookContext,
    ) -> None:
        """Timeout with on_timeout=block returns BLOCK."""
        hook_def = config.HookDefinition(
            name="test-hook",
            type="command",
            command="sleep 10",
            timeout=config.HookTimeoutConfig(seconds=1, on_timeout="block"),
        )

        result = await executor.execute(hook_def, context)
        assert result.action == events.HookAction.BLOCK
        assert "timed out" in result.message.lower()  # type: ignore[union-attr]

    @_pytest.mark.asyncio
    async def test_timeout_triggers_continue(
        self,
        executor: command_executor.CommandHookExecutor,
        context: events.HookContext,
    ) -> None:
        """Timeout with on_timeout=continue returns CONTINUE."""
        hook_def = config.HookDefinition(
            name="test-hook",
            type="command",
            command="sleep 10",
            timeout=config.HookTimeoutConfig(seconds=1, on_timeout="continue"),
        )

        result = await executor.execute(hook_def, context)
        assert result.action == events.HookAction.CONTINUE

    @_pytest.mark.asyncio
    async def test_cwd_is_context_cwd(
        self,
        executor: command_executor.CommandHookExecutor,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Command runs in context's cwd."""
        # Create a unique file in tmp_path
        marker_file = tmp_path / "marker.txt"
        marker_file.write_text("marker")

        context = events.HookContext(
            event=events.HookEvent.PRE_TOOL_USE,
            session_id="test-session",
            cwd=tmp_path,
            tool="Bash",
        )

        hook_def = config.HookDefinition(
            name="test-hook",
            type="command",
            command="test -f marker.txt",
        )

        result = await executor.execute(hook_def, context)
        assert result.action == events.HookAction.CONTINUE

