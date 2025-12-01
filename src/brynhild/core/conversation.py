"""
Unified conversation processing for Brynhild.

This module provides a single implementation of the conversation loop
that handles streaming, thinking, tool execution, and multi-round interactions.
Both TUI and CLI modes use this via appropriate callbacks.
"""

import abc as _abc
import dataclasses as _dataclasses
import pathlib as _pathlib
import typing as _typing

import brynhild.api.base as api_base
import brynhild.api.types as api_types
import brynhild.constants as _constants
import brynhild.core.types as core_types
import brynhild.hooks.events as hooks_events
import brynhild.hooks.manager as hooks_manager
import brynhild.logging as brynhild_logging
import brynhild.tools.base as tools_base
import brynhild.tools.registry as tools_registry


@_dataclasses.dataclass
class ConversationResult:
    """Result of processing a conversation turn."""

    response_text: str
    """The final assistant response text."""

    thinking: str | None
    """Thinking/reasoning trace if available."""

    tool_uses: list[api_types.ToolUse]
    """Tool uses that were executed."""

    tool_results: list[tools_base.ToolResult]
    """Results from tool executions."""

    input_tokens: int
    """Total input tokens used."""

    output_tokens: int
    """Total output tokens used."""

    stop_reason: str | None
    """Why the model stopped generating."""

    cancelled: bool = False
    """Whether the generation was cancelled by the user."""

    messages: list[dict[str, _typing.Any]] = _dataclasses.field(default_factory=list)
    """Updated message history after this turn (for caller synchronization)."""


class ConversationCallbacks(_abc.ABC):
    """
    Abstract callbacks for conversation processing UI integration.

    Different UI modes (TUI, CLI, JSON) implement these to control
    how the conversation is displayed and how interactions happen.
    """

    # === Streaming lifecycle ===

    @_abc.abstractmethod
    async def on_stream_start(self) -> None:
        """Called when streaming begins."""
        ...

    @_abc.abstractmethod
    async def on_stream_end(self) -> None:
        """Called when streaming ends."""
        ...

    # === Thinking callbacks ===

    @_abc.abstractmethod
    async def on_thinking_delta(self, text: str) -> None:
        """Called for each thinking token.

        Args:
            text: The thinking text delta.
        """
        ...

    @_abc.abstractmethod
    async def on_thinking_complete(self, full_text: str) -> None:
        """Called when thinking is complete (text starts).

        Args:
            full_text: The complete thinking text.
        """
        ...

    # === Response text callbacks ===

    @_abc.abstractmethod
    async def on_text_delta(self, text: str) -> None:
        """Called for each response text token.

        Args:
            text: The response text delta.
        """
        ...

    @_abc.abstractmethod
    async def on_text_complete(self, full_text: str, thinking: str | None) -> None:
        """Called when response text is complete.

        Args:
            full_text: The complete response text.
            thinking: The thinking text if any.
        """
        ...

    # === Tool callbacks ===

    @_abc.abstractmethod
    async def on_tool_call(self, tool_call: core_types.ToolCallDisplay) -> None:
        """Called when a tool is about to be executed.

        Args:
            tool_call: Information about the tool call.
        """
        ...

    @_abc.abstractmethod
    async def request_tool_permission(
        self,
        tool_call: core_types.ToolCallDisplay,
    ) -> bool:
        """Request permission to execute a tool.

        Args:
            tool_call: Information about the tool call.

        Returns:
            True if permission granted, False otherwise.
        """
        ...

    @_abc.abstractmethod
    async def on_tool_result(self, result: core_types.ToolResultDisplay) -> None:
        """Called after a tool is executed.

        Args:
            result: The tool result to display.
        """
        ...

    # === Round lifecycle ===

    @_abc.abstractmethod
    async def on_round_start(self, round_num: int) -> None:
        """Called at the start of each tool round.

        Args:
            round_num: The round number (1-indexed).
        """
        ...

    # === Cancellation ===

    def is_cancelled(self) -> bool:
        """Check if the user has requested cancellation.

        Returns:
            True if cancelled, False otherwise.
        """
        return False

    # === Info/debug ===

    async def on_info(self, message: str) -> None:  # noqa: B027
        """Called for informational messages.

        Args:
            message: The info message.
        """
        pass  # Optional, default no-op


class ConversationProcessor:
    """
    Unified conversation processing for all UI modes.

    This class consolidates the conversation loop logic that was previously
    duplicated between app.py (TUI) and runner.py (CLI).
    """

    def __init__(
        self,
        provider: api_base.LLMProvider,
        callbacks: ConversationCallbacks,
        *,
        tool_registry: tools_registry.ToolRegistry | None = None,
        max_tokens: int = _constants.DEFAULT_MAX_TOKENS,
        max_tool_rounds: int = _constants.DEFAULT_MAX_TOOL_ROUNDS,
        auto_approve_tools: bool = False,
        dry_run: bool = False,
        logger: brynhild_logging.ConversationLogger | None = None,
        hook_manager: hooks_manager.HookManager | None = None,
        session_id: str = "",
        cwd: _pathlib.Path | None = None,
    ) -> None:
        """
        Initialize the conversation processor.

        Args:
            provider: LLM provider instance.
            callbacks: UI callbacks for display and interaction.
            tool_registry: Tool registry (None to disable tools).
            max_tokens: Maximum tokens for responses.
            max_tool_rounds: Maximum rounds of tool execution.
            auto_approve_tools: Auto-approve all tool executions.
            dry_run: Show tool calls without executing.
            logger: Conversation logger instance.
            hook_manager: Optional hook manager for lifecycle events.
            session_id: Session ID for hook context.
            cwd: Working directory for hook context.
        """
        self._provider = provider
        self._callbacks = callbacks
        self._tool_registry = tool_registry
        self._max_tokens = max_tokens
        self._max_tool_rounds = max_tool_rounds
        self._auto_approve = auto_approve_tools
        self._dry_run = dry_run
        self._logger = logger
        self._hook_manager = hook_manager
        self._session_id = session_id
        self._cwd = cwd or _pathlib.Path.cwd()

        # Track pending injections from hooks
        self._pending_injections: list[str] = []

    def _get_tools_for_api(self) -> list[api_types.Tool] | None:
        """Get tool definitions for the API call."""
        if self._tool_registry is None:
            return None

        # Check if provider supports tools
        if not self._provider.supports_tools():
            return None

        tools: list[api_types.Tool] = []
        for tool in self._tool_registry.list_tools():
            tools.append(
                api_types.Tool(
                    name=tool.name,
                    description=tool.description,
                    input_schema=tool.get_input_schema(),
                )
            )
        return tools if tools else None

    async def _execute_tool(
        self,
        tool_use: api_types.ToolUse,
    ) -> tools_base.ToolResult:
        """Execute a single tool call."""
        # Start with original input (may be modified by hooks)
        tool_input = tool_use.input

        # Dispatch pre_tool_use hook
        if self._hook_manager:
            pre_context = hooks_events.HookContext(
                event=hooks_events.HookEvent.PRE_TOOL_USE,
                session_id=self._session_id,
                cwd=self._cwd,
                tool=tool_use.name,
                tool_input=tool_input,
            )
            hook_result = await self._hook_manager.dispatch(
                hooks_events.HookEvent.PRE_TOOL_USE,
                pre_context,
            )

            # Check if hook blocked
            if hook_result.action == hooks_events.HookAction.BLOCK:
                return self._make_error_result(
                    tool_use,
                    hook_result.message or "Blocked by pre_tool_use hook",
                )
            if hook_result.action == hooks_events.HookAction.SKIP:
                return self._make_success_result(
                    tool_use,
                    "[skipped by pre_tool_use hook]",
                )

            # Apply input modifications
            if hook_result.modified_input is not None:
                tool_input = hook_result.modified_input

            # Handle inject_system_message from pre_tool_use hook
            if hook_result.inject_system_message:
                self._pending_injections.append(hook_result.inject_system_message)
                if self._logger:
                    self._logger.log_context_injection(
                        source="hook",
                        location="message_inject",
                        content=hook_result.inject_system_message,
                        origin="pre_tool_use",
                        trigger_type="auto",
                    )

        # Log tool call
        if self._logger:
            self._logger.log_tool_call(
                tool_name=tool_use.name,
                tool_input=tool_input,
                tool_id=tool_use.id,
            )

        # Check registry exists
        if self._tool_registry is None:
            return self._make_error_result(tool_use, "No tool registry configured")

        # Look up tool
        tool = self._tool_registry.get(tool_use.name)
        if tool is None:
            return self._make_error_result(tool_use, f"Unknown tool: {tool_use.name}")

        # Create display object (with potentially modified input)
        tool_call_display = core_types.ToolCallDisplay(
            tool_name=tool_use.name,
            tool_input=tool_input,
            tool_id=tool_use.id,
        )

        # Show the tool call
        await self._callbacks.on_tool_call(tool_call_display)

        # Handle dry run
        if self._dry_run:
            return self._make_success_result(tool_use, "[dry run - tool not executed]")

        # Check permission (skip for tools that don't require it)
        if tool.requires_permission:
            if self._auto_approve:
                pass  # Auto-approved
            elif not await self._callbacks.request_tool_permission(tool_call_display):
                return self._make_error_result(tool_use, "Permission denied by user")

        # Execute the tool
        try:
            result = await tool.execute(tool_input)
            self._log_result(tool_use, result)

            # Dispatch post_tool_use hook
            if self._hook_manager:
                post_context = hooks_events.HookContext(
                    event=hooks_events.HookEvent.POST_TOOL_USE,
                    session_id=self._session_id,
                    cwd=self._cwd,
                    tool=tool_use.name,
                    tool_input=tool_input,
                    tool_result=result,
                )
                post_hook_result = await self._hook_manager.dispatch(
                    hooks_events.HookEvent.POST_TOOL_USE,
                    post_context,
                )

                # Apply output modifications
                if post_hook_result.modified_output is not None:
                    result = tools_base.ToolResult(
                        success=result.success,
                        output=post_hook_result.modified_output,
                        error=result.error,
                    )

                # Handle inject_system_message from post_tool_use hook
                if post_hook_result.inject_system_message:
                    self._pending_injections.append(post_hook_result.inject_system_message)
                    if self._logger:
                        self._logger.log_context_injection(
                            source="hook",
                            location="message_inject",
                            content=post_hook_result.inject_system_message,
                            origin="post_tool_use",
                            trigger_type="auto",
                        )

            # Show result
            result_display = core_types.ToolResultDisplay(
                tool_name=tool_use.name,
                result=result,
                tool_id=tool_use.id,
            )
            await self._callbacks.on_tool_result(result_display)

            return result
        except Exception as e:
            return self._make_error_result(tool_use, str(e))

    def _make_error_result(
        self,
        tool_use: api_types.ToolUse,
        error: str,
    ) -> tools_base.ToolResult:
        """Create and log an error result."""
        result = tools_base.ToolResult(success=False, output="", error=error)
        self._log_result(tool_use, result)
        return result

    def _make_success_result(
        self,
        tool_use: api_types.ToolUse,
        output: str,
    ) -> tools_base.ToolResult:
        """Create and log a success result."""
        result = tools_base.ToolResult(success=True, output=output, error=None)
        self._log_result(tool_use, result)
        return result

    def _log_result(
        self,
        tool_use: api_types.ToolUse,
        result: tools_base.ToolResult,
    ) -> None:
        """Log a tool result if logger is configured."""
        if self._logger:
            self._logger.log_tool_result(
                tool_name=tool_use.name,
                success=result.success,
                output=result.output if result.success else None,
                error=result.error,
                tool_id=tool_use.id,
            )

    def _apply_pending_injections(
        self,
        working_messages: list[dict[str, _typing.Any]],
    ) -> None:
        """
        Apply any pending injections to the message history.

        Injections are added as system-style user messages before the
        LLM call. This ensures the LLM sees the injected content
        (guidance, skill content, etc.) in context.
        """
        if not self._pending_injections:
            return

        # Combine all pending injections into a single message
        combined = "\n\n".join(self._pending_injections)

        # Add as a user message with system-like framing
        injection_message = {
            "role": "user",
            "content": f"[System guidance]\n{combined}\n[/System guidance]\n\nPlease continue with the task, taking this guidance into account.",
        }
        working_messages.append(injection_message)

        # Clear pending injections
        self._pending_injections.clear()

    async def process_streaming(
        self,
        messages: list[dict[str, _typing.Any]],
        system_prompt: str,
    ) -> ConversationResult:
        """
        Process a conversation turn with streaming.

        Args:
            messages: The message history.
            system_prompt: The system prompt.

        Returns:
            ConversationResult with the response and metadata.
        """
        tools = self._get_tools_for_api()
        tool_round = 0
        final_response = ""
        final_thinking: str | None = None
        stop_reason: str | None = None
        total_input = 0
        total_output = 0
        all_tool_uses: list[api_types.ToolUse] = []
        all_tool_results: list[tools_base.ToolResult] = []

        # Working copy of messages for tool rounds
        working_messages = list(messages)

        while tool_round < self._max_tool_rounds:
            tool_round += 1
            await self._callbacks.on_round_start(tool_round)

            # Check cancellation
            if self._callbacks.is_cancelled():
                return ConversationResult(
                    response_text=final_response,
                    thinking=final_thinking,
                    tool_uses=all_tool_uses,
                    tool_results=all_tool_results,
                    input_tokens=total_input,
                    output_tokens=total_output,
                    stop_reason="cancelled",
                    cancelled=True,
                    messages=working_messages,
                )

            # Apply any pending injections before LLM call
            self._apply_pending_injections(working_messages)

            # Start streaming
            await self._callbacks.on_stream_start()
            current_text = ""
            current_thinking = ""
            tool_uses: list[api_types.ToolUse] = []
            usage: api_types.Usage | None = None

            try:
                async for event in self._provider.stream(
                    messages=working_messages,
                    system=system_prompt,
                    max_tokens=self._max_tokens,
                    tools=tools,
                ):
                    # Check cancellation
                    if self._callbacks.is_cancelled():
                        await self._callbacks.on_stream_end()
                        return ConversationResult(
                            response_text=final_response + current_text,
                            thinking=current_thinking or final_thinking,
                            tool_uses=all_tool_uses,
                            tool_results=all_tool_results,
                            input_tokens=total_input,
                            output_tokens=total_output,
                            stop_reason="cancelled",
                            cancelled=True,
                            messages=working_messages,
                        )

                    if event.type == "thinking_delta" and event.thinking:
                        current_thinking += event.thinking
                        await self._callbacks.on_thinking_delta(event.thinking)

                    elif event.type == "text_delta" and event.text:
                        # First text after thinking - signal thinking complete
                        if current_thinking and not current_text:
                            await self._callbacks.on_thinking_complete(current_thinking)
                        current_text += event.text
                        await self._callbacks.on_text_delta(event.text)

                    elif event.type == "tool_use_start" and event.tool_use:
                        tool_uses.append(event.tool_use)

                    elif event.type == "content_stop":
                        # Some providers send tool uses on content_stop
                        if event.tool_use:
                            tool_uses.append(event.tool_use)
                        stop_reason = event.stop_reason
                        usage = event.usage

            except Exception as e:
                await self._callbacks.on_stream_end()
                await self._callbacks.on_info(f"Error: {e}")
                raise

            await self._callbacks.on_stream_end()

            # Update totals
            if usage:
                total_input += usage.input_tokens
                total_output += usage.output_tokens

            # Log thinking
            if current_thinking and self._logger:
                self._logger.log_thinking(current_thinking)
                final_thinking = current_thinking

            # Handle response
            if current_text:
                final_response = current_text
                working_messages.append({"role": "assistant", "content": current_text})
                await self._callbacks.on_text_complete(current_text, current_thinking)

                # Log assistant response
                if self._logger:
                    self._logger.log_assistant_message(
                        current_text,
                        thinking=current_thinking if current_thinking else None,
                    )

            # No tool calls - we're done
            if not tool_uses:
                break

            # Process tool calls
            tool_results: list[dict[str, _typing.Any]] = []

            for tool_use in tool_uses:
                # Check cancellation
                if self._callbacks.is_cancelled():
                    return ConversationResult(
                        response_text=final_response,
                        thinking=final_thinking,
                        tool_uses=all_tool_uses,
                        tool_results=all_tool_results,
                        input_tokens=total_input,
                        output_tokens=total_output,
                        stop_reason="cancelled",
                        cancelled=True,
                        messages=working_messages,
                    )

                tool_result = await self._execute_tool(tool_use)
                all_tool_uses.append(tool_use)
                all_tool_results.append(tool_result)

                # Format result for next round
                tool_results.append(
                    core_types.format_tool_result_message(tool_use.id, tool_result)
                )

            # Add tool results to messages for next round
            working_messages.append({"role": "user", "content": tool_results})

        return ConversationResult(
            response_text=final_response,
            thinking=final_thinking,
            tool_uses=all_tool_uses,
            tool_results=all_tool_results,
            input_tokens=total_input,
            output_tokens=total_output,
            stop_reason=stop_reason,
            messages=working_messages,
        )

    async def process_complete(
        self,
        messages: list[dict[str, _typing.Any]],
        system_prompt: str,
    ) -> ConversationResult:
        """
        Process a conversation turn without streaming.

        Args:
            messages: The message history.
            system_prompt: The system prompt.

        Returns:
            ConversationResult with the response and metadata.
        """
        tools = self._get_tools_for_api()
        tool_round = 0
        final_response = ""
        final_thinking: str | None = None
        stop_reason: str | None = None
        total_input = 0
        total_output = 0
        all_tool_uses: list[api_types.ToolUse] = []
        all_tool_results: list[tools_base.ToolResult] = []

        # Working copy of messages for tool rounds
        working_messages = list(messages)

        while tool_round < self._max_tool_rounds:
            tool_round += 1
            await self._callbacks.on_round_start(tool_round)

            # Check cancellation
            if self._callbacks.is_cancelled():
                return ConversationResult(
                    response_text=final_response,
                    thinking=final_thinking,
                    tool_uses=all_tool_uses,
                    tool_results=all_tool_results,
                    input_tokens=total_input,
                    output_tokens=total_output,
                    stop_reason="cancelled",
                    cancelled=True,
                    messages=working_messages,
                )

            # Apply any pending injections before LLM call
            self._apply_pending_injections(working_messages)

            # Make completion request
            response = await self._provider.complete(
                messages=working_messages,
                system=system_prompt,
                max_tokens=self._max_tokens,
                tools=tools,
            )

            # Update totals
            if response.usage:
                total_input += response.usage.input_tokens
                total_output += response.usage.output_tokens

            stop_reason = response.stop_reason

            # Handle thinking
            if response.thinking:
                final_thinking = response.thinking
                await self._callbacks.on_thinking_complete(response.thinking)
                if self._logger:
                    self._logger.log_thinking(response.thinking)

            # Handle response text
            if response.content:
                final_response = response.content
                working_messages.append({"role": "assistant", "content": response.content})
                await self._callbacks.on_text_complete(response.content, response.thinking)

                # Log assistant response
                if self._logger:
                    self._logger.log_assistant_message(
                        response.content,
                        thinking=response.thinking,
                    )

            # No tool calls - we're done
            if not response.tool_uses:
                break

            # Process tool calls
            tool_results: list[dict[str, _typing.Any]] = []

            for tool_use in response.tool_uses:
                # Check cancellation
                if self._callbacks.is_cancelled():
                    return ConversationResult(
                        response_text=final_response,
                        thinking=final_thinking,
                        tool_uses=all_tool_uses,
                        tool_results=all_tool_results,
                        input_tokens=total_input,
                        output_tokens=total_output,
                        stop_reason="cancelled",
                        cancelled=True,
                        messages=working_messages,
                    )

                tool_result = await self._execute_tool(tool_use)
                all_tool_uses.append(tool_use)
                all_tool_results.append(tool_result)

                # Format result for next round
                tool_results.append(
                    core_types.format_tool_result_message(tool_use.id, tool_result)
                )

            # Add tool results to messages for next round
            working_messages.append({"role": "user", "content": tool_results})

        return ConversationResult(
            response_text=final_response,
            thinking=final_thinking,
            tool_uses=all_tool_uses,
            tool_results=all_tool_results,
            input_tokens=total_input,
            output_tokens=total_output,
            stop_reason=stop_reason,
            messages=working_messages,
        )

