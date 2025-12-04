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
import brynhild.core.tool_recovery as tool_recovery
import brynhild.core.types as core_types
import brynhild.hooks.events as hooks_events
import brynhild.hooks.manager as hooks_manager
import brynhild.logging as brynhild_logging
import brynhild.profiles.types as profiles_types
import brynhild.tools.base as tools_base
import brynhild.tools.registry as tools_registry


def _is_valid_tool_use(tool_use: api_types.ToolUse) -> bool:
    """Check if a tool use has required fields populated.

    Malformed tool uses from providers (e.g., missing name or id) are
    silently dropped to prevent downstream errors.

    Args:
        tool_use: The tool use to validate.

    Returns:
        True if valid, False if malformed.
    """
    if not tool_use:
        return False
    if not tool_use.name or not isinstance(tool_use.name, str):
        return False
    if not tool_use.id or not isinstance(tool_use.id, str):
        return False
    return tool_use.input is not None and isinstance(tool_use.input, dict)


@_dataclasses.dataclass
class RecoveryConfig:
    """Configuration for tool call recovery from thinking text."""

    enabled: bool = False
    """Whether to attempt recovery of tool calls from thinking text."""

    feedback_enabled: bool = True
    """Whether to inject feedback after recovering a tool call."""

    requires_intent_phrase: bool = False
    """Whether to require intent phrases near JSON for recovery."""

    max_recoveries_per_session: int = 20
    """Maximum number of recoveries allowed per session."""

    max_recoveries_per_turn: int = 3
    """Maximum number of recoveries allowed per turn."""

    @classmethod
    def from_profile(cls, profile: profiles_types.ModelProfile) -> "RecoveryConfig":
        """Create RecoveryConfig from a model profile.

        Args:
            profile: Model profile with recovery settings.

        Returns:
            RecoveryConfig populated from profile flags.
        """
        return cls(
            enabled=profile.enable_tool_recovery,
            feedback_enabled=profile.recovery_feedback_enabled,
            requires_intent_phrase=profile.recovery_requires_intent_phrase,
        )


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
        recovery_config: RecoveryConfig | None = None,
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
            recovery_config: Configuration for tool call recovery from thinking.
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
        self._recovery_config = recovery_config or RecoveryConfig()

        # Track pending injections from hooks
        self._pending_injections: list[str] = []

        # Tool metrics collector
        self._metrics = tools_base.MetricsCollector()

        # Recovery tracking state
        self._recovery_count_session: int = 0
        self._recovery_count_turn: int = 0
        self._recent_recovered_hashes: set[str] = set()
        self._last_turn_had_recovery: bool = False

    @property
    def metrics(self) -> tools_base.MetricsCollector:
        """Get the metrics collector for this processor."""
        return self._metrics

    def _can_recover_tool_call(self) -> bool:
        """Check if recovery is allowed given current budgets."""
        if not self._recovery_config.enabled:
            return False
        if self._recovery_count_session >= self._recovery_config.max_recoveries_per_session:
            return False
        return self._recovery_count_turn < self._recovery_config.max_recoveries_per_turn

    def _hash_tool_call(self, tool_use: api_types.ToolUse) -> str:
        """Create a hash for loop detection."""
        # Sort dict items for consistent hashing
        try:
            args_str = str(sorted(tool_use.input.items()))
        except (AttributeError, TypeError):
            args_str = str(tool_use.input)
        return f"{tool_use.name}:{args_str}"

    def _is_recovery_loop(self, tool_use: api_types.ToolUse) -> bool:
        """Check if this would be a repeated recovery (loop detection)."""
        h = self._hash_tool_call(tool_use)
        return h in self._recent_recovered_hashes

    def _record_recovery(self, tool_use: api_types.ToolUse) -> None:
        """Record a successful recovery for tracking."""
        self._recovery_count_session += 1
        self._recovery_count_turn += 1
        self._recent_recovered_hashes.add(self._hash_tool_call(tool_use))
        self._last_turn_had_recovery = True

    def _clear_recovery_hashes_on_native(self) -> None:
        """Clear recovery hashes when a native tool call occurs."""
        # Native tool call indicates state change - clear loop detection
        self._recent_recovered_hashes.clear()

    @property
    def recovery_count(self) -> int:
        """Return the number of tool calls recovered this session."""
        return self._recovery_count_session

    def _reset_turn_recovery_count(self) -> None:
        """Reset per-turn recovery count at start of new turn."""
        self._recovery_count_turn = 0

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
                    input_schema=tool.input_schema,
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
                logger=self._logger,
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

        # Log tool call - detect if this was a recovered call by ID prefix
        if self._logger:
            call_type = "recovered" if tool_use.id.startswith("recovered-") else "native"
            self._logger.log_tool_call(
                tool_name=tool_use.name,
                tool_input=tool_input,
                tool_id=tool_use.id,
                call_type=call_type,
            )

        # Check registry exists
        if self._tool_registry is None:
            return self._make_error_result(tool_use, "No tool registry configured")

        # Look up tool
        tool = self._tool_registry.get(tool_use.name)
        if tool is None:
            return self._make_error_result(tool_use, f"Unknown tool: {tool_use.name}")

        # Create display object (with potentially modified input)
        # Detect if this is a recovered call by checking ID prefix
        is_recovered = tool_use.id.startswith("recovered-")
        tool_call_display = core_types.ToolCallDisplay(
            tool_name=tool_use.name,
            tool_input=tool_input,
            tool_id=tool_use.id,
            is_recovered=is_recovered,
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

        # Execute the tool with timing
        import time as _time

        start_time = _time.perf_counter()
        try:
            result = await tool.execute(tool_input)
            duration_ms = (_time.perf_counter() - start_time) * 1000

            # Record metrics
            self._metrics.record(tool_use.name, result.success, duration_ms)

            self._log_result(tool_use, result)

            # Dispatch post_tool_use hook with metrics
            if self._hook_manager:
                # Get metrics for this tool and overall summary
                tool_metrics = self._metrics.get(tool_use.name)
                session_summary = self._metrics.summary()

                post_context = hooks_events.HookContext(
                    event=hooks_events.HookEvent.POST_TOOL_USE,
                    session_id=self._session_id,
                    cwd=self._cwd,
                    tool=tool_use.name,
                    tool_input=tool_input,
                    tool_result=result,
                    tool_metrics=tool_metrics,
                    session_metrics_summary=session_summary,
                    logger=self._logger,
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
            duration_ms = (_time.perf_counter() - start_time) * 1000
            self._metrics.record(tool_use.name, False, duration_ms)
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

    def _apply_recovery_feedback(
        self,
        working_messages: list[dict[str, _typing.Any]],
    ) -> None:
        """
        Apply recovery feedback if last turn had a recovered tool call.

        This helps the model learn to emit tool calls via the proper channel
        instead of placing them in thinking text.
        """
        if not self._last_turn_had_recovery:
            return

        if not self._recovery_config.feedback_enabled:
            self._last_turn_had_recovery = False
            return

        # Inject feedback message
        feedback_message = {
            "role": "user",
            "content": (
                "[System Note]\n"
                "In your previous response, you placed tool call arguments in your thinking/analysis "
                "instead of emitting a proper tool call. Brynhild recovered and executed the tool for you. "
                "In future responses, please emit tool calls using the tool call mechanism (via the "
                "tool_calls channel) rather than including tool JSON in your analysis.\n"
                "[/System Note]\n\n"
                "Please continue with the task."
            ),
        }
        working_messages.append(feedback_message)

        # Log the feedback injection
        if self._logger:
            self._logger.log_event(
                "recovery_feedback_injected",
                session_recovery_count=self._recovery_count_session,
            )

        # Clear the flag
        self._last_turn_had_recovery = False

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

            # Reset per-turn recovery count at start of each round
            self._reset_turn_recovery_count()

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
            self._apply_recovery_feedback(working_messages)

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
                        # Validate tool_use has required fields
                        if _is_valid_tool_use(event.tool_use):
                            tool_uses.append(event.tool_use)
                        # Silently skip malformed tool uses (logged at trace level)

                    elif event.type == "content_stop":
                        # Some providers send tool uses on content_stop
                        if event.tool_use and _is_valid_tool_use(event.tool_use):
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

            # Try to recover tool calls from thinking if none were emitted
            # Some models put tool call JSON in thinking instead of emitting properly
            if not tool_uses and current_thinking and self._tool_registry:
                if self._can_recover_tool_call():
                    recovery = tool_recovery.try_recover_tool_call_from_thinking(
                        current_thinking,
                        self._tool_registry,
                        model_recovery_enabled=True,  # Already checked in _can_recover
                    )
                    if recovery:
                        # Check for recovery loop (same tool+args repeated)
                        if self._is_recovery_loop(recovery.tool_use):
                            await self._callbacks.on_info(
                                f"Recovery loop detected: {recovery.tool_use.name} - stopping recovery"
                            )
                            if self._logger:
                                self._logger.log_event(
                                    "recovery_loop_detected",
                                    tool_name=recovery.tool_use.name,
                                )
                        # Check if confirmation is required
                        elif recovery.requires_confirmation:
                            await self._callbacks.on_info(
                                f"Recovered tool call requires confirmation: {recovery.tool_use.name} "
                                f"(risk: {recovery.tool_risk_level})"
                            )
                            # For now, skip tools requiring confirmation
                            # TODO: Add confirmation flow
                        else:
                            tool_uses.append(recovery.tool_use)
                            self._record_recovery(recovery.tool_use)
                            await self._callbacks.on_info(
                                f"Recovered tool call from thinking: {recovery.tool_use.name} "
                                f"(type: {recovery.recovery_type}, risk: {recovery.tool_risk_level})"
                            )
                        if self._logger:
                            self._logger.log_event(
                                "tool_call_recovered",
                                **recovery.to_log_dict(),
                            )
                elif self._recovery_config.enabled:
                    # Budget exceeded
                    if self._logger:
                        self._logger.log_event(
                            "recovery_budget_exceeded",
                            session_count=self._recovery_count_session,
                            turn_count=self._recovery_count_turn,
                        )

            # Handle response text and/or tool calls
            if tool_uses:
                # Clear loop detection hashes when native tool calls occur
                if not self._last_turn_had_recovery:
                    self._clear_recovery_hashes_on_native()
                # Model returned tool calls - add assistant message with tool_calls
                # This is required for OpenAI-compatible APIs to associate tool
                # results with the calls that generated them
                working_messages.append(
                    core_types.format_assistant_tool_call(tool_uses, current_text)
                )

                if current_text:
                    final_response = current_text
                    await self._callbacks.on_text_complete(current_text, current_thinking)

                    # Log assistant response
                    if self._logger:
                        self._logger.log_assistant_message(
                            current_text,
                            thinking=current_thinking if current_thinking else None,
                        )

                # Execute tools and add results as individual messages
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

                    # Add tool result as individual message for next round
                    working_messages.append(
                        core_types.format_tool_result_message(tool_use.id, tool_result)
                    )

            elif current_text:
                # No tool calls, just text response - we're done
                final_response = current_text
                working_messages.append({"role": "assistant", "content": current_text})
                await self._callbacks.on_text_complete(current_text, current_thinking)

                # Log assistant response
                if self._logger:
                    self._logger.log_assistant_message(
                        current_text,
                        thinking=current_thinking if current_thinking else None,
                    )
                break
            else:
                # No text and no tool calls - unexpected but handle gracefully
                break

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

            # Reset per-turn recovery count at start of each round
            self._reset_turn_recovery_count()

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
            self._apply_recovery_feedback(working_messages)

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

            # Get tool uses, with recovery from thinking if needed
            tool_uses = list(response.tool_uses) if response.tool_uses else []

            # Try to recover tool calls from thinking if none were emitted
            # Some models put tool call JSON in thinking instead of emitting properly
            if not tool_uses and response.thinking and self._tool_registry:
                if self._can_recover_tool_call():
                    recovery = tool_recovery.try_recover_tool_call_from_thinking(
                        response.thinking,
                        self._tool_registry,
                        model_recovery_enabled=True,  # Already checked in _can_recover
                    )
                    if recovery:
                        # Check for recovery loop (same tool+args repeated)
                        if self._is_recovery_loop(recovery.tool_use):
                            await self._callbacks.on_info(
                                f"Recovery loop detected: {recovery.tool_use.name} - stopping recovery"
                            )
                            if self._logger:
                                self._logger.log_event(
                                    "recovery_loop_detected",
                                    tool_name=recovery.tool_use.name,
                                )
                        # Check if confirmation is required
                        elif recovery.requires_confirmation:
                            await self._callbacks.on_info(
                                f"Recovered tool call requires confirmation: {recovery.tool_use.name} "
                                f"(risk: {recovery.tool_risk_level})"
                            )
                            # For now, skip tools requiring confirmation
                            # TODO: Add confirmation flow
                        else:
                            tool_uses.append(recovery.tool_use)
                            self._record_recovery(recovery.tool_use)
                            await self._callbacks.on_info(
                                f"Recovered tool call from thinking: {recovery.tool_use.name} "
                                f"(type: {recovery.recovery_type}, risk: {recovery.tool_risk_level})"
                            )
                        if self._logger:
                            self._logger.log_event(
                                "tool_call_recovered",
                                **recovery.to_log_dict(),
                            )
                elif self._recovery_config.enabled:
                    # Budget exceeded
                    if self._logger:
                        self._logger.log_event(
                            "recovery_budget_exceeded",
                            session_count=self._recovery_count_session,
                            turn_count=self._recovery_count_turn,
                        )

            # Handle response text and/or tool calls
            if tool_uses:
                # Clear loop detection hashes when native tool calls occur
                if not self._last_turn_had_recovery:
                    self._clear_recovery_hashes_on_native()
                # Model returned tool calls - add assistant message with tool_calls
                # This is required for OpenAI-compatible APIs to associate tool
                # results with the calls that generated them
                working_messages.append(
                    core_types.format_assistant_tool_call(
                        tool_uses, response.content or ""
                    )
                )

                if response.content:
                    final_response = response.content
                    await self._callbacks.on_text_complete(
                        response.content, response.thinking
                    )

                    # Log assistant response
                    if self._logger:
                        self._logger.log_assistant_message(
                            response.content,
                            thinking=response.thinking,
                        )

                # Execute tools and add results as individual messages
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

                    # Add tool result as individual message for next round
                    working_messages.append(
                        core_types.format_tool_result_message(tool_use.id, tool_result)
                    )

            elif response.content:
                # No tool calls, just text response - we're done
                final_response = response.content
                working_messages.append(
                    {"role": "assistant", "content": response.content}
                )
                await self._callbacks.on_text_complete(
                    response.content, response.thinking
                )

                # Log assistant response
                if self._logger:
                    self._logger.log_assistant_message(
                        response.content,
                        thinking=response.thinking,
                    )
                break
            else:
                # No text and no tool calls - unexpected but handle gracefully
                break

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

