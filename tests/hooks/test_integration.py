"""Integration tests for hook system with conversation processor."""

import pathlib as _pathlib

import pytest as _pytest

import brynhild.api.types as api_types
import brynhild.core.conversation as conversation
import brynhild.hooks.config as config
import brynhild.hooks.manager as manager
import brynhild.tools.base as tools_base
import brynhild.tools.registry as registry


class MockTool(tools_base.Tool):
    """A mock tool for testing."""

    @property
    def name(self) -> str:
        return "MockTool"

    @property
    def description(self) -> str:
        return "A mock tool for testing"

    @property
    def requires_permission(self) -> bool:
        return False  # Don't require permission for tests

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "input": {"type": "string"},
            },
        }

    async def execute(self, input: dict) -> tools_base.ToolResult:
        return tools_base.ToolResult(
            success=True,
            output=f"Executed with: {input.get('input', 'no input')}",
        )


class MockCallbacks(conversation.ConversationCallbacks):
    """Mock callbacks for testing."""

    def __init__(self) -> None:
        self.tool_calls: list = []
        self.tool_results: list = []

    async def on_stream_start(self) -> None:
        pass

    async def on_stream_end(self) -> None:
        pass

    async def on_thinking_delta(self, text: str) -> None:
        pass

    async def on_thinking_complete(self, full_text: str) -> None:
        pass

    async def on_text_delta(self, text: str) -> None:
        pass

    async def on_text_complete(self, full_text: str, thinking: str | None) -> None:
        pass

    async def on_tool_call(self, tool_call: conversation.core_types.ToolCallDisplay) -> None:
        self.tool_calls.append(tool_call)

    async def request_tool_permission(
        self,
        tool_call: conversation.core_types.ToolCallDisplay,  # noqa: ARG002
    ) -> bool:
        return True

    async def on_tool_result(
        self,
        result: conversation.core_types.ToolResultDisplay,
    ) -> None:
        self.tool_results.append(result)

    async def on_round_start(self, round_num: int) -> None:
        pass


class MockProvider:
    """Mock LLM provider for testing."""

    @property
    def name(self) -> str:
        return "mock"

    @property
    def model(self) -> str:
        return "mock-model"

    def supports_tools(self) -> bool:
        return True


class TestHookIntegration:
    """Tests for hook integration with ConversationProcessor."""

    @_pytest.fixture
    def tool_registry(self) -> registry.ToolRegistry:
        """Create a registry with our mock tool."""
        reg = registry.ToolRegistry()
        reg.register(MockTool())
        return reg

    @_pytest.fixture
    def callbacks(self) -> MockCallbacks:
        return MockCallbacks()

    @_pytest.fixture
    def provider(self) -> MockProvider:
        return MockProvider()

    @_pytest.mark.asyncio
    async def test_pre_tool_use_hook_can_block(
        self,
        tool_registry: registry.ToolRegistry,
        callbacks: MockCallbacks,
        provider: MockProvider,
        tmp_path: _pathlib.Path,
    ) -> None:
        """pre_tool_use hook can block tool execution."""
        # Create a blocking hook
        hook = config.HookDefinition(
            name="blocker",
            type="command",
            command="exit 1",
            message="Blocked by test hook",
            match={"tool": "MockTool"},
        )
        hooks_config = config.HooksConfig(hooks={"pre_tool_use": [hook]})
        hook_mgr = manager.HookManager(hooks_config, project_root=tmp_path)

        processor = conversation.ConversationProcessor(
            provider=provider,  # type: ignore[arg-type]
            callbacks=callbacks,
            tool_registry=tool_registry,
            hook_manager=hook_mgr,
            session_id="test-session",
            cwd=tmp_path,
        )

        # Execute a tool
        tool_use = api_types.ToolUse(
            id="test-id",
            name="MockTool",
            input={"input": "test value"},
        )
        result = await processor._execute_tool(tool_use)

        # Hook should have blocked
        assert result.success is False
        assert "Blocked by test hook" in (result.error or "")

    @_pytest.mark.asyncio
    async def test_pre_tool_use_hook_can_skip(
        self,
        tool_registry: registry.ToolRegistry,
        callbacks: MockCallbacks,
        provider: MockProvider,
        tmp_path: _pathlib.Path,
    ) -> None:
        """pre_tool_use hook can skip tool execution (via exit 0)."""
        # A hook that continues normally (exit 0)
        hook = config.HookDefinition(
            name="logger",
            type="command",
            command="exit 0",  # Continue
        )
        hooks_config = config.HooksConfig(hooks={"pre_tool_use": [hook]})
        hook_mgr = manager.HookManager(hooks_config, project_root=tmp_path)

        processor = conversation.ConversationProcessor(
            provider=provider,  # type: ignore[arg-type]
            callbacks=callbacks,
            tool_registry=tool_registry,
            hook_manager=hook_mgr,
            session_id="test-session",
            cwd=tmp_path,
        )

        # Execute a tool
        tool_use = api_types.ToolUse(
            id="test-id",
            name="MockTool",
            input={"input": "test value"},
        )
        result = await processor._execute_tool(tool_use)

        # Tool should execute normally
        assert result.success is True
        assert "test value" in result.output

    @_pytest.mark.asyncio
    async def test_multiple_hooks_run_sequentially(
        self,
        tool_registry: registry.ToolRegistry,
        callbacks: MockCallbacks,
        provider: MockProvider,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Multiple hooks run in sequence, first blocker wins."""
        # First hook continues
        hook1 = config.HookDefinition(
            name="hook1",
            type="command",
            command="exit 0",  # Continue
        )
        # Second hook blocks
        hook2 = config.HookDefinition(
            name="hook2",
            type="command",
            command="exit 1",  # Block
            message="Blocked by hook2",
        )
        hooks_config = config.HooksConfig(hooks={"pre_tool_use": [hook1, hook2]})
        hook_mgr = manager.HookManager(hooks_config, project_root=tmp_path)

        processor = conversation.ConversationProcessor(
            provider=provider,  # type: ignore[arg-type]
            callbacks=callbacks,
            tool_registry=tool_registry,
            hook_manager=hook_mgr,
            session_id="test-session",
            cwd=tmp_path,
        )

        # Execute a tool
        tool_use = api_types.ToolUse(
            id="test-id",
            name="MockTool",
            input={"input": "test"},
        )
        result = await processor._execute_tool(tool_use)

        # Second hook should have blocked
        assert result.success is False
        assert "Blocked by hook2" in (result.error or "")

    @_pytest.mark.asyncio
    async def test_hook_match_filtering(
        self,
        tool_registry: registry.ToolRegistry,
        callbacks: MockCallbacks,
        provider: MockProvider,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Hooks only fire when match conditions are met."""
        # Create a hook that only matches OtherTool (not MockTool)
        hook = config.HookDefinition(
            name="other-tool-blocker",
            type="command",
            command="exit 1",
            message="Should not see this",
            match={"tool": "OtherTool"},  # Won't match MockTool
        )
        hooks_config = config.HooksConfig(hooks={"pre_tool_use": [hook]})
        hook_mgr = manager.HookManager(hooks_config, project_root=tmp_path)

        processor = conversation.ConversationProcessor(
            provider=provider,  # type: ignore[arg-type]
            callbacks=callbacks,
            tool_registry=tool_registry,
            hook_manager=hook_mgr,
            session_id="test-session",
            cwd=tmp_path,
        )

        # Execute MockTool - should NOT be blocked
        tool_use = api_types.ToolUse(
            id="test-id",
            name="MockTool",
            input={"input": "test"},
        )
        result = await processor._execute_tool(tool_use)

        # Hook should not have blocked
        assert result.success is True

    @_pytest.mark.asyncio
    async def test_no_hooks_works_normally(
        self,
        tool_registry: registry.ToolRegistry,
        callbacks: MockCallbacks,
        provider: MockProvider,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Tool execution works when no hook manager is configured."""
        processor = conversation.ConversationProcessor(
            provider=provider,  # type: ignore[arg-type]
            callbacks=callbacks,
            tool_registry=tool_registry,
            # No hook_manager
            session_id="test-session",
            cwd=tmp_path,
        )

        # Execute a tool
        tool_use = api_types.ToolUse(
            id="test-id",
            name="MockTool",
            input={"input": "test"},
        )
        result = await processor._execute_tool(tool_use)

        # Should work normally
        assert result.success is True
        assert "test" in result.output

