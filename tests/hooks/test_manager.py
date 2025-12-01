"""Tests for HookManager."""

import pathlib as _pathlib

import pytest as _pytest

import brynhild.hooks.config as config
import brynhild.hooks.events as events
import brynhild.hooks.manager as manager


class TestHookManager:
    """Tests for HookManager class."""

    @_pytest.fixture
    def empty_manager(self) -> manager.HookManager:
        """Create manager with no hooks."""
        return manager.HookManager.construct_empty()

    def test_empty_manager_has_no_hooks(
        self,
        empty_manager: manager.HookManager,
    ) -> None:
        """Empty manager reports no hooks for any event."""
        assert not empty_manager.has_hooks_for_event(events.HookEvent.PRE_TOOL_USE)
        assert not empty_manager.has_hooks_for_event(events.HookEvent.SESSION_START)

    @_pytest.mark.asyncio
    async def test_empty_manager_returns_continue(
        self,
        empty_manager: manager.HookManager,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Empty manager always returns CONTINUE."""
        context = events.HookContext(
            event=events.HookEvent.PRE_TOOL_USE,
            session_id="test",
            cwd=tmp_path,
            tool="Bash",
        )
        result = await empty_manager.dispatch(events.HookEvent.PRE_TOOL_USE, context)
        assert result.action == events.HookAction.CONTINUE

    def test_manager_with_hooks(self) -> None:
        """Manager reports hooks when configured."""
        hook = config.HookDefinition(
            name="test-hook",
            type="command",
            command="echo test",
        )
        hooks_config = config.HooksConfig(hooks={"pre_tool_use": [hook]})
        mgr = manager.HookManager(hooks_config)

        assert mgr.has_hooks_for_event(events.HookEvent.PRE_TOOL_USE)
        assert not mgr.has_hooks_for_event(events.HookEvent.SESSION_START)

    @_pytest.mark.asyncio
    async def test_hook_execution_continue(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Hook returning exit 0 results in CONTINUE."""
        hook = config.HookDefinition(
            name="test-hook",
            type="command",
            command="exit 0",
        )
        hooks_config = config.HooksConfig(hooks={"pre_tool_use": [hook]})
        mgr = manager.HookManager(hooks_config, project_root=tmp_path)

        context = events.HookContext(
            event=events.HookEvent.PRE_TOOL_USE,
            session_id="test",
            cwd=tmp_path,
            tool="Bash",
        )
        result = await mgr.dispatch(events.HookEvent.PRE_TOOL_USE, context)
        assert result.action == events.HookAction.CONTINUE

    @_pytest.mark.asyncio
    async def test_hook_execution_block(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Hook returning non-zero exit results in BLOCK."""
        hook = config.HookDefinition(
            name="test-hook",
            type="command",
            command="exit 1",
            message="Blocked by test",
        )
        hooks_config = config.HooksConfig(hooks={"pre_tool_use": [hook]})
        mgr = manager.HookManager(hooks_config, project_root=tmp_path)

        context = events.HookContext(
            event=events.HookEvent.PRE_TOOL_USE,
            session_id="test",
            cwd=tmp_path,
            tool="Bash",
        )
        result = await mgr.dispatch(events.HookEvent.PRE_TOOL_USE, context)
        assert result.action == events.HookAction.BLOCK
        assert result.message == "Blocked by test"

    @_pytest.mark.asyncio
    async def test_hooks_run_sequentially(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Multiple hooks run in definition order."""
        # Create a file to track execution order
        order_file = tmp_path / "order.txt"

        hook1 = config.HookDefinition(
            name="hook1",
            type="command",
            command=f"echo 1 >> {order_file}",
        )
        hook2 = config.HookDefinition(
            name="hook2",
            type="command",
            command=f"echo 2 >> {order_file}",
        )
        hooks_config = config.HooksConfig(hooks={"pre_tool_use": [hook1, hook2]})
        mgr = manager.HookManager(hooks_config, project_root=tmp_path)

        context = events.HookContext(
            event=events.HookEvent.PRE_TOOL_USE,
            session_id="test",
            cwd=tmp_path,
            tool="Bash",
        )
        await mgr.dispatch(events.HookEvent.PRE_TOOL_USE, context)

        # Verify order
        content = order_file.read_text().strip()
        lines = content.split("\n")
        assert lines == ["1", "2"]

    @_pytest.mark.asyncio
    async def test_block_stops_subsequent_hooks(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """BLOCK result stops execution of subsequent hooks."""
        marker_file = tmp_path / "marker.txt"

        hook1 = config.HookDefinition(
            name="blocker",
            type="command",
            command="exit 1",
            message="Blocked",
        )
        hook2 = config.HookDefinition(
            name="marker",
            type="command",
            command=f"touch {marker_file}",
        )
        hooks_config = config.HooksConfig(hooks={"pre_tool_use": [hook1, hook2]})
        mgr = manager.HookManager(hooks_config, project_root=tmp_path)

        context = events.HookContext(
            event=events.HookEvent.PRE_TOOL_USE,
            session_id="test",
            cwd=tmp_path,
            tool="Bash",
        )
        result = await mgr.dispatch(events.HookEvent.PRE_TOOL_USE, context)

        assert result.action == events.HookAction.BLOCK
        assert not marker_file.exists()  # Second hook should not have run

    @_pytest.mark.asyncio
    async def test_match_filtering(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Hooks with non-matching conditions are skipped."""
        hook = config.HookDefinition(
            name="bash-only",
            type="command",
            command="exit 1",  # Would block if run
            match={"tool": "Bash"},
        )
        hooks_config = config.HooksConfig(hooks={"pre_tool_use": [hook]})
        mgr = manager.HookManager(hooks_config, project_root=tmp_path)

        # Context with different tool - hook should be skipped
        context = events.HookContext(
            event=events.HookEvent.PRE_TOOL_USE,
            session_id="test",
            cwd=tmp_path,
            tool="Read",  # Not Bash
        )
        result = await mgr.dispatch(events.HookEvent.PRE_TOOL_USE, context)
        assert result.action == events.HookAction.CONTINUE

    @_pytest.mark.asyncio
    async def test_block_ignored_for_non_blocking_event(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Block action is ignored for events that cannot block."""
        hook = config.HookDefinition(
            name="blocker",
            type="command",
            command="exit 1",
            message="Should be ignored",
        )
        hooks_config = config.HooksConfig(hooks={"session_start": [hook]})
        mgr = manager.HookManager(hooks_config, project_root=tmp_path)

        context = events.HookContext(
            event=events.HookEvent.SESSION_START,
            session_id="test",
            cwd=tmp_path,
        )
        # SESSION_START cannot be blocked
        result = await mgr.dispatch(events.HookEvent.SESSION_START, context)
        assert result.action == events.HookAction.CONTINUE

    @_pytest.mark.asyncio
    async def test_hook_error_continues(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Hook execution errors don't block, just continue."""
        # Script hook with non-existent script should error
        hook = config.HookDefinition(
            name="broken",
            type="script",
            script="nonexistent.py",
        )
        hooks_config = config.HooksConfig(hooks={"pre_tool_use": [hook]})
        mgr = manager.HookManager(hooks_config, project_root=tmp_path)

        context = events.HookContext(
            event=events.HookEvent.PRE_TOOL_USE,
            session_id="test",
            cwd=tmp_path,
            tool="Bash",
        )
        # Should not raise, should continue
        result = await mgr.dispatch(events.HookEvent.PRE_TOOL_USE, context)
        assert result.action == events.HookAction.CONTINUE


class TestHookFailureSemantics:
    """Tests documenting hook failure behavior."""

    @_pytest.mark.asyncio
    async def test_command_hook_nonzero_exit_blocks(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Command hook with non-zero exit code should BLOCK."""
        hook = config.HookDefinition(
            name="blocking-command",
            type="command",
            command="exit 1",
            message="Blocked by test hook",
        )
        hooks_config = config.HooksConfig(hooks={"pre_tool_use": [hook]})
        mgr = manager.HookManager(hooks_config, project_root=tmp_path)

        context = events.HookContext(
            event=events.HookEvent.PRE_TOOL_USE,
            session_id="test",
            cwd=tmp_path,
            tool="Bash",
        )
        result = await mgr.dispatch(events.HookEvent.PRE_TOOL_USE, context)

        assert result.action == events.HookAction.BLOCK
        assert result.message == "Blocked by test hook"

    @_pytest.mark.asyncio
    async def test_command_hook_zero_exit_continues(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Command hook with zero exit code should CONTINUE."""
        hook = config.HookDefinition(
            name="passing-command",
            type="command",
            command="exit 0",
        )
        hooks_config = config.HooksConfig(hooks={"pre_tool_use": [hook]})
        mgr = manager.HookManager(hooks_config, project_root=tmp_path)

        context = events.HookContext(
            event=events.HookEvent.PRE_TOOL_USE,
            session_id="test",
            cwd=tmp_path,
            tool="Bash",
        )
        result = await mgr.dispatch(events.HookEvent.PRE_TOOL_USE, context)

        assert result.action == events.HookAction.CONTINUE

    @_pytest.mark.asyncio
    async def test_script_exception_continues_not_blocks(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Script hook that raises exception should continue (not block)."""
        # Create a script that raises an exception
        script_file = tmp_path / "bad_script.py"
        script_file.write_text("raise RuntimeError('Script failed!')")

        hook = config.HookDefinition(
            name="exception-script",
            type="script",
            script=str(script_file),
        )
        hooks_config = config.HooksConfig(hooks={"pre_tool_use": [hook]})
        mgr = manager.HookManager(hooks_config, project_root=tmp_path)

        context = events.HookContext(
            event=events.HookEvent.PRE_TOOL_USE,
            session_id="test",
            cwd=tmp_path,
            tool="Bash",
        )
        # Exception should be caught, hook continues
        result = await mgr.dispatch(events.HookEvent.PRE_TOOL_USE, context)

        assert result.action == events.HookAction.CONTINUE

    @_pytest.mark.asyncio
    async def test_multiple_hooks_error_in_first_continues_to_second(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Error in first hook should not prevent second hook from running."""
        # First hook errors
        error_hook = config.HookDefinition(
            name="error-hook",
            type="script",
            script="nonexistent.py",
        )
        # Second hook blocks
        block_hook = config.HookDefinition(
            name="block-hook",
            type="command",
            command="exit 1",
            message="Second hook blocked",
        )
        hooks_config = config.HooksConfig(
            hooks={"pre_tool_use": [error_hook, block_hook]}
        )
        mgr = manager.HookManager(hooks_config, project_root=tmp_path)

        context = events.HookContext(
            event=events.HookEvent.PRE_TOOL_USE,
            session_id="test",
            cwd=tmp_path,
            tool="Bash",
        )
        result = await mgr.dispatch(events.HookEvent.PRE_TOOL_USE, context)

        # First hook errored and continued, second hook should run and block
        assert result.action == events.HookAction.BLOCK
        assert result.message == "Second hook blocked"

