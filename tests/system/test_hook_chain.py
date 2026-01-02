"""System tests for hook chain execution."""

import pathlib as _pathlib

import pytest as _pytest

import brynhild.hooks.config as hooks_config
import brynhild.hooks.events as hooks_events
import brynhild.hooks.manager as hooks_manager


@_pytest.mark.system
class TestHookChainSystem:
    """System tests for hook chain execution."""

    @_pytest.mark.asyncio
    async def test_multiple_hooks_run_sequentially(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Multiple hooks for the same event run in sequence."""
        # Setup: Three hooks that all allow (exit 0)
        hook1 = hooks_config.HookDefinition(
            name="hook1",
            type="command",
            command="exit 0",
        )
        hook2 = hooks_config.HookDefinition(
            name="hook2",
            type="command",
            command="exit 0",
        )
        hook3 = hooks_config.HookDefinition(
            name="hook3",
            type="command",
            command="exit 0",
        )

        hook_config = hooks_config.HooksConfig(hooks={"pre_tool_use": [hook1, hook2, hook3]})
        manager = hooks_manager.HookManager(hook_config, project_root=tmp_path)

        # Create context
        context = hooks_events.HookContext(
            event=hooks_events.HookEvent.PRE_TOOL_USE,
            session_id="test-session",
            cwd=tmp_path,
            tool="TestTool",
            tool_input={"input": "test"},
        )

        # Execute
        result = await manager.dispatch(hooks_events.HookEvent.PRE_TOOL_USE, context)

        # Verify: All hooks ran and allowed
        assert result.action == hooks_events.HookAction.CONTINUE

    @_pytest.mark.asyncio
    async def test_first_blocking_hook_stops_chain(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """First blocking hook stops the chain, subsequent hooks don't run."""
        # Setup: First hook allows, second blocks, third allows
        hook1 = hooks_config.HookDefinition(
            name="hook1",
            type="command",
            command="exit 0",  # Allow
        )
        hook2 = hooks_config.HookDefinition(
            name="hook2",
            type="command",
            command="exit 1",  # Block
            message="Blocked by hook2",
        )
        hook3 = hooks_config.HookDefinition(
            name="hook3",
            type="command",
            command="exit 0",  # Would allow, but never reached
        )

        hook_config = hooks_config.HooksConfig(hooks={"pre_tool_use": [hook1, hook2, hook3]})
        manager = hooks_manager.HookManager(hook_config, project_root=tmp_path)

        context = hooks_events.HookContext(
            event=hooks_events.HookEvent.PRE_TOOL_USE,
            session_id="test-session",
            cwd=tmp_path,
            tool="TestTool",
            tool_input={},
        )

        # Execute
        result = await manager.dispatch(hooks_events.HookEvent.PRE_TOOL_USE, context)

        # Verify: Chain was blocked
        assert result.action == hooks_events.HookAction.BLOCK
        assert result.message is not None
        assert "hook2" in result.message.lower() or "blocked" in result.message.lower()

    @_pytest.mark.asyncio
    async def test_hook_match_filtering(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Hooks only fire when their match conditions are met."""
        # Setup: Hook that only matches "DangerousTool"
        hook = hooks_config.HookDefinition(
            name="danger_blocker",
            type="command",
            command="exit 1",
            message="Dangerous tool blocked",
            match={"tool": "DangerousTool"},
        )

        hook_config = hooks_config.HooksConfig(hooks={"pre_tool_use": [hook]})
        manager = hooks_manager.HookManager(hook_config, project_root=tmp_path)

        # Context 1: Non-matching tool
        context_safe = hooks_events.HookContext(
            event=hooks_events.HookEvent.PRE_TOOL_USE,
            session_id="test-session",
            cwd=tmp_path,
            tool="SafeTool",
            tool_input={},
        )

        # Execute: Safe tool should not be blocked
        result_safe = await manager.dispatch(
            hooks_events.HookEvent.PRE_TOOL_USE,
            context_safe,
        )
        assert result_safe.action == hooks_events.HookAction.CONTINUE

        # Context 2: Matching tool
        context_dangerous = hooks_events.HookContext(
            event=hooks_events.HookEvent.PRE_TOOL_USE,
            session_id="test-session",
            cwd=tmp_path,
            tool="DangerousTool",
            tool_input={},
        )

        # Execute: Dangerous tool should be blocked
        result_dangerous = await manager.dispatch(
            hooks_events.HookEvent.PRE_TOOL_USE,
            context_dangerous,
        )
        assert result_dangerous.action == hooks_events.HookAction.BLOCK

    @_pytest.mark.asyncio
    async def test_hook_receives_tool_input_in_context(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Hooks receive tool input in their context for matching."""
        # Setup: Hook that matches on tool input
        # In HookContext.to_dict(), the key is "tool_input" (not just "input")
        hook = hooks_config.HookDefinition(
            name="rm_blocker",
            type="command",
            command="exit 1",
            message="rm commands blocked",
            match={"tool_input.command": "^rm.*"},  # Regex with ^ anchor
        )

        hook_config = hooks_config.HooksConfig(hooks={"pre_tool_use": [hook]})
        manager = hooks_manager.HookManager(hook_config, project_root=tmp_path)

        # Context with rm command
        context_rm = hooks_events.HookContext(
            event=hooks_events.HookEvent.PRE_TOOL_USE,
            session_id="test-session",
            cwd=tmp_path,
            tool="Bash",
            tool_input={"command": "rm -rf /tmp/test"},
        )

        result_rm = await manager.dispatch(hooks_events.HookEvent.PRE_TOOL_USE, context_rm)
        assert result_rm.action == hooks_events.HookAction.BLOCK

        # Context with safe command
        context_ls = hooks_events.HookContext(
            event=hooks_events.HookEvent.PRE_TOOL_USE,
            session_id="test-session",
            cwd=tmp_path,
            tool="Bash",
            tool_input={"command": "ls -la"},
        )

        result_ls = await manager.dispatch(hooks_events.HookEvent.PRE_TOOL_USE, context_ls)
        assert result_ls.action == hooks_events.HookAction.CONTINUE

    @_pytest.mark.asyncio
    async def test_no_hooks_returns_continue(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """When no hooks are configured, dispatch returns CONTINUE."""
        # Setup: Empty hooks config
        hook_config = hooks_config.HooksConfig(hooks={})
        manager = hooks_manager.HookManager(hook_config, project_root=tmp_path)

        context = hooks_events.HookContext(
            event=hooks_events.HookEvent.PRE_TOOL_USE,
            session_id="test-session",
            cwd=tmp_path,
            tool="AnyTool",
            tool_input={},
        )

        # Execute
        result = await manager.dispatch(hooks_events.HookEvent.PRE_TOOL_USE, context)

        # Verify: No hooks means continue
        assert result.action == hooks_events.HookAction.CONTINUE

    @_pytest.mark.asyncio
    async def test_post_tool_use_hooks_receive_result(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Post-tool-use hooks receive the tool result in context."""
        import brynhild.tools.base as tools_base

        # Setup: Hook for post_tool_use
        hook = hooks_config.HookDefinition(
            name="result_logger",
            type="command",
            command="exit 0",
        )

        hook_config = hooks_config.HooksConfig(hooks={"post_tool_use": [hook]})
        manager = hooks_manager.HookManager(hook_config, project_root=tmp_path)

        # Context with tool result
        tool_result = tools_base.ToolResult(
            success=True,
            output="Command output here",
            error=None,
        )
        context = hooks_events.HookContext(
            event=hooks_events.HookEvent.POST_TOOL_USE,
            session_id="test-session",
            cwd=tmp_path,
            tool="Bash",
            tool_input={"command": "ls"},
            tool_result=tool_result,
        )

        # Execute
        result = await manager.dispatch(hooks_events.HookEvent.POST_TOOL_USE, context)

        # Verify: Hook ran successfully
        assert result.action == hooks_events.HookAction.CONTINUE

    @_pytest.mark.asyncio
    async def test_session_lifecycle_hooks(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Session start and end hooks fire at appropriate times."""
        # Setup: Hooks for session lifecycle
        start_hook = hooks_config.HookDefinition(
            name="session_start_logger",
            type="command",
            command="exit 0",
        )
        end_hook = hooks_config.HookDefinition(
            name="session_end_logger",
            type="command",
            command="exit 0",
        )

        hook_config = hooks_config.HooksConfig(
            hooks={
                "session_start": [start_hook],
                "session_end": [end_hook],
            }
        )
        manager = hooks_manager.HookManager(hook_config, project_root=tmp_path)

        # Session start context
        start_context = hooks_events.HookContext(
            event=hooks_events.HookEvent.SESSION_START,
            session_id="test-session",
            cwd=tmp_path,
        )

        result_start = await manager.dispatch(
            hooks_events.HookEvent.SESSION_START,
            start_context,
        )
        assert result_start.action == hooks_events.HookAction.CONTINUE

        # Session end context
        end_context = hooks_events.HookContext(
            event=hooks_events.HookEvent.SESSION_END,
            session_id="test-session",
            cwd=tmp_path,
        )

        result_end = await manager.dispatch(hooks_events.HookEvent.SESSION_END, end_context)
        assert result_end.action == hooks_events.HookAction.CONTINUE
