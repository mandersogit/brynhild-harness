"""
Shared tool execution logic for Brynhild.

This module provides a unified tool execution implementation that can be
used by both interactive (TUI) and non-interactive (CLI) modes.
"""

import abc as _abc
import time as _time

import brynhild.api.types as api_types
import brynhild.core.types as core_types
import brynhild.logging as brynhild_logging
import brynhild.tools.base as tools_base
import brynhild.tools.registry as tools_registry


class ToolExecutionCallbacks(_abc.ABC):
    """
    Abstract callbacks for tool execution UI integration.

    Different UI modes (TUI, CLI, JSON) implement these to control
    how tool calls are displayed and how permissions are requested.
    """

    @_abc.abstractmethod
    async def show_tool_call(self, tool_call: core_types.ToolCallDisplay) -> None:
        """Display that a tool is about to be called.

        Args:
            tool_call: Information about the tool call.
        """
        ...

    @_abc.abstractmethod
    async def request_permission(
        self,
        tool_call: core_types.ToolCallDisplay,
        *,
        auto_approve: bool = False,
    ) -> bool:
        """Request permission to execute a tool.

        Args:
            tool_call: Information about the tool call.
            auto_approve: If True, automatically approve without prompting.

        Returns:
            True if permission granted, False otherwise.
        """
        ...

    @_abc.abstractmethod
    async def show_tool_result(self, result: core_types.ToolResultDisplay) -> None:
        """Display the result of a tool execution.

        Args:
            result: The tool result to display.
        """
        ...


class ToolExecutor:
    """
    Executes tools with consistent permission checking and logging.

    This class consolidates the tool execution logic that was previously
    duplicated between app.py (TUI) and runner.py (CLI).

    Tool metrics are always collected during execution.
    """

    def __init__(
        self,
        tool_registry: tools_registry.ToolRegistry | None,
        callbacks: ToolExecutionCallbacks,
        *,
        dry_run: bool = False,
        logger: brynhild_logging.ConversationLogger | None = None,
    ) -> None:
        """
        Initialize the tool executor.

        Args:
            tool_registry: Registry of available tools.
            callbacks: UI callbacks for display and permission.
            dry_run: If True, show tool calls but don't execute.
            logger: Optional conversation logger.
        """
        self._registry = tool_registry
        self._callbacks = callbacks
        self._dry_run = dry_run
        self._logger = logger
        self._metrics = tools_base.MetricsCollector()

    @property
    def metrics(self) -> tools_base.MetricsCollector:
        """Get the metrics collector for this executor."""
        return self._metrics

    async def execute(
        self,
        tool_use: api_types.ToolUse,
    ) -> tools_base.ToolResult:
        """
        Execute a single tool call.

        Handles:
        - Tool lookup
        - Display of tool call
        - Permission checking (respecting requires_permission)
        - Dry run mode
        - Execution and error handling
        - Logging

        Args:
            tool_use: The tool use request from the LLM.

        Returns:
            The result of tool execution.
        """
        # Log tool call
        if self._logger:
            self._logger.log_tool_call(
                tool_name=tool_use.name,
                tool_input=tool_use.input,
                tool_id=tool_use.id,
            )

        # Check registry exists
        if self._registry is None:
            return self._make_error_result(
                tool_use,
                "No tool registry configured",
            )

        # Look up tool
        tool = self._registry.get(tool_use.name)
        if tool is None:
            return self._make_error_result(
                tool_use,
                f"Unknown tool: {tool_use.name}",
            )

        # Create display object
        tool_call_display = core_types.ToolCallDisplay(
            tool_name=tool_use.name,
            tool_input=tool_use.input,
            tool_id=tool_use.id,
        )

        # Show the tool call
        await self._callbacks.show_tool_call(tool_call_display)

        # Handle dry run
        if self._dry_run:
            return self._make_success_result(
                tool_use,
                "[dry run - tool not executed]",
            )

        # Check permission (skip for tools that don't require it)
        if tool.requires_permission and not await self._callbacks.request_permission(
            tool_call_display
        ):
            return self._make_error_result(
                tool_use,
                "Permission denied by user",
            )

        # Validate input against schema
        validation = tool.validate_input(tool_use.input)
        if not validation.is_valid:
            return self._make_error_result(
                tool_use,
                f"Invalid input: {'; '.join(validation.errors)}",
            )

        # Execute the tool with metrics
        start_time = _time.perf_counter()
        try:
            result = await tool.execute(tool_use.input)
            duration_ms = (_time.perf_counter() - start_time) * 1000
            self._metrics.record(tool_use.name, result.success, duration_ms)

            # Prepend warnings to output so LLM gets feedback about unknown params
            if validation.has_warnings:
                warning_text = "⚠️ " + "; ".join(validation.warnings) + "\n\n"
                result = tools_base.ToolResult(
                    success=result.success,
                    output=warning_text + result.output,
                    error=result.error,
                )

            self._log_result(tool_use, result, duration_ms)
            return result
        except Exception as e:
            duration_ms = (_time.perf_counter() - start_time) * 1000
            self._metrics.record(tool_use.name, False, duration_ms)
            return self._make_error_result(tool_use, str(e), duration_ms)

    def _make_error_result(
        self,
        tool_use: api_types.ToolUse,
        error: str,
        duration_ms: float | None = None,
    ) -> tools_base.ToolResult:
        """Create and log an error result."""
        result = tools_base.ToolResult(
            success=False,
            output="",
            error=error,
        )
        self._log_result(tool_use, result, duration_ms)
        return result

    def _make_success_result(
        self,
        tool_use: api_types.ToolUse,
        output: str,
        duration_ms: float | None = None,
    ) -> tools_base.ToolResult:
        """Create and log a success result."""
        result = tools_base.ToolResult(
            success=True,
            output=output,
            error=None,
        )
        self._log_result(tool_use, result, duration_ms)
        return result

    def _log_result(
        self,
        tool_use: api_types.ToolUse,
        result: tools_base.ToolResult,
        duration_ms: float | None = None,
    ) -> None:
        """Log a tool result if logger is configured."""
        if self._logger:
            self._logger.log_tool_result(
                tool_name=tool_use.name,
                success=result.success,
                output=result.output if result.success else None,
                error=result.error,
                tool_id=tool_use.id,
                duration_ms=duration_ms,
            )

