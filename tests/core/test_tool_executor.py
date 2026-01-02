"""Tests for core/tool_executor.py."""

import typing as _typing

import pytest as _pytest

import brynhild.api.types as api_types
import brynhild.core.tool_executor as tool_executor
import brynhild.tools.base as tools_base
import brynhild.tools.registry as tools_registry
import brynhild.ui.base as ui_base


class MockTool(tools_base.Tool):
    """A mock tool for testing."""

    def __init__(
        self,
        name: str = "MockTool",
        requires_permission: bool = True,
        execute_result: tools_base.ToolResult | None = None,
        execute_exception: Exception | None = None,
    ) -> None:
        self._name = name
        self._requires_permission = requires_permission
        self._execute_result = execute_result or tools_base.ToolResult(
            success=True, output="mock output", error=None
        )
        self._execute_exception = execute_exception
        self.execute_called = False
        self.execute_input: dict[str, _typing.Any] | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "A mock tool for testing"

    @property
    def requires_permission(self) -> bool:
        return self._requires_permission

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, input: dict[str, _typing.Any]) -> tools_base.ToolResult:
        self.execute_called = True
        self.execute_input = input
        if self._execute_exception:
            raise self._execute_exception
        return self._execute_result


class MockCallbacks(tool_executor.ToolExecutionCallbacks):
    """Mock callbacks for testing."""

    def __init__(self, grant_permission: bool = True) -> None:
        self.grant_permission = grant_permission
        self.tool_calls: list[ui_base.ToolCallDisplay] = []
        self.permission_requests: list[ui_base.ToolCallDisplay] = []
        self.tool_results: list[ui_base.ToolResultDisplay] = []

    async def show_tool_call(self, tool_call: ui_base.ToolCallDisplay) -> None:
        self.tool_calls.append(tool_call)

    async def request_permission(
        self,
        tool_call: ui_base.ToolCallDisplay,
        *,
        auto_approve: bool = False,  # noqa: ARG002
    ) -> bool:
        self.permission_requests.append(tool_call)
        return self.grant_permission

    async def show_tool_result(self, result: ui_base.ToolResultDisplay) -> None:
        self.tool_results.append(result)


class TestToolExecutor:
    """Tests for ToolExecutor."""

    def _make_tool_use(
        self,
        name: str = "MockTool",
        input: dict[str, _typing.Any] | None = None,
    ) -> api_types.ToolUse:
        return api_types.ToolUse(
            id="test-id-123",
            name=name,
            input=input or {},
        )

    @_pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        """Tool executes successfully."""
        tool = MockTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)
        callbacks = MockCallbacks()

        executor = tool_executor.ToolExecutor(
            tool_registry=registry,
            callbacks=callbacks,
        )

        result = await executor.execute(self._make_tool_use())

        assert result.success is True
        assert result.output == "mock output"
        assert tool.execute_called

    @_pytest.mark.asyncio
    async def test_execute_unknown_tool(self) -> None:
        """Unknown tool returns error."""
        registry = tools_registry.ToolRegistry()
        callbacks = MockCallbacks()

        executor = tool_executor.ToolExecutor(
            tool_registry=registry,
            callbacks=callbacks,
        )

        result = await executor.execute(self._make_tool_use("NonExistent"))

        assert result.success is False
        assert "Unknown tool" in (result.error or "")

    @_pytest.mark.asyncio
    async def test_execute_no_registry(self) -> None:
        """No registry returns error."""
        callbacks = MockCallbacks()

        executor = tool_executor.ToolExecutor(
            tool_registry=None,
            callbacks=callbacks,
        )

        result = await executor.execute(self._make_tool_use())

        assert result.success is False
        assert "No tool registry" in (result.error or "")

    @_pytest.mark.asyncio
    async def test_execute_dry_run(self) -> None:
        """Dry run doesn't execute tool."""
        tool = MockTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)
        callbacks = MockCallbacks()

        executor = tool_executor.ToolExecutor(
            tool_registry=registry,
            callbacks=callbacks,
            dry_run=True,
        )

        result = await executor.execute(self._make_tool_use())

        assert result.success is True
        assert "dry run" in result.output
        assert not tool.execute_called

    @_pytest.mark.asyncio
    async def test_execute_permission_denied(self) -> None:
        """Permission denied returns error."""
        tool = MockTool(requires_permission=True)
        registry = tools_registry.ToolRegistry()
        registry.register(tool)
        callbacks = MockCallbacks(grant_permission=False)

        executor = tool_executor.ToolExecutor(
            tool_registry=registry,
            callbacks=callbacks,
        )

        result = await executor.execute(self._make_tool_use())

        assert result.success is False
        assert "Permission denied" in (result.error or "")
        assert not tool.execute_called

    @_pytest.mark.asyncio
    async def test_execute_no_permission_required(self) -> None:
        """Tool with requires_permission=False skips permission."""
        tool = MockTool(requires_permission=False)
        registry = tools_registry.ToolRegistry()
        registry.register(tool)
        callbacks = MockCallbacks(grant_permission=False)  # Would deny if asked

        executor = tool_executor.ToolExecutor(
            tool_registry=registry,
            callbacks=callbacks,
        )

        result = await executor.execute(self._make_tool_use())

        assert result.success is True  # Executed despite callback saying no
        assert len(callbacks.permission_requests) == 0  # Never asked

    @_pytest.mark.asyncio
    async def test_execute_exception_caught(self) -> None:
        """Exception during execution is caught."""
        tool = MockTool(execute_exception=RuntimeError("boom"))
        registry = tools_registry.ToolRegistry()
        registry.register(tool)
        callbacks = MockCallbacks()

        executor = tool_executor.ToolExecutor(
            tool_registry=registry,
            callbacks=callbacks,
        )

        result = await executor.execute(self._make_tool_use())

        assert result.success is False
        assert "boom" in (result.error or "")

    @_pytest.mark.asyncio
    async def test_callbacks_called_in_order(self) -> None:
        """Callbacks are called in the right order."""
        tool = MockTool()
        registry = tools_registry.ToolRegistry()
        registry.register(tool)
        callbacks = MockCallbacks()

        executor = tool_executor.ToolExecutor(
            tool_registry=registry,
            callbacks=callbacks,
        )

        await executor.execute(self._make_tool_use())

        # ToolExecutor calls show_tool_call and request_permission
        # It does NOT call show_tool_result (that's done by ConversationProcessor)
        assert len(callbacks.tool_calls) == 1
        assert len(callbacks.permission_requests) == 1
        assert callbacks.tool_calls[0].tool_name == "MockTool"
