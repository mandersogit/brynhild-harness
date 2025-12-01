"""Tests for script hook executor."""

import pathlib as _pathlib

import pydantic as _pydantic
import pytest as _pytest

import brynhild.hooks.config as config
import brynhild.hooks.events as events
import brynhild.hooks.executors.base as base
import brynhild.hooks.executors.script as script_executor

# Script tests require subprocess execution which may be blocked by sandbox
# Mark these as slow to allow skipping in fast test runs
pytestmark = _pytest.mark.slow


class TestScriptHookExecutor:
    """Tests for ScriptHookExecutor."""

    @_pytest.fixture
    def executor(self, tmp_path: _pathlib.Path) -> script_executor.ScriptHookExecutor:
        """Create executor with tmp_path as project root."""
        return script_executor.ScriptHookExecutor(project_root=tmp_path)

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

    def test_hook_type_is_script(self) -> None:
        """ScriptHookExecutor has correct hook_type."""
        executor = script_executor.ScriptHookExecutor()
        assert executor.hook_type == "script"

    def test_no_script_raises_validation_error(self) -> None:
        """Hook without script field raises pydantic ValidationError."""
        with _pytest.raises(_pydantic.ValidationError, match="script"):
            config.HookDefinition(
                name="no-script",
                type="script",
                # No script field - pydantic validates at creation
            )

    @_pytest.mark.asyncio
    async def test_script_not_found_raises_error(
        self,
        executor: script_executor.ScriptHookExecutor,
        context: events.HookContext,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Missing script raises HookExecutionError."""
        hook_def = config.HookDefinition(
            name="missing-script",
            type="script",
            script=str(tmp_path / "nonexistent.py"),
        )

        with _pytest.raises(base.HookExecutionError, match="not found"):
            await executor.execute(hook_def, context)

