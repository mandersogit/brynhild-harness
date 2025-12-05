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
import brynhild.core.message_validators as message_validators
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

    finish_result: "FinishResult | None" = None
    """Explicit finish signal if Finish tool was called."""


@_dataclasses.dataclass
class FinishResult:
    """Result from an explicit Finish tool call."""

    status: str
    """Completion status: success, partial, failed, blocked."""

    summary: str
    """Summary of what was accomplished or why incomplete."""

    next_steps: str | None = None
    """Optional suggestions for the user's next actions."""


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

    # === Usage tracking ===

    async def on_usage_update(  # noqa: B027
        self,
        input_tokens: int,
        output_tokens: int,
        usage: "api_types.Usage | None" = None,
    ) -> None:
        """Called after each API call with token usage.

        This is called during the tool loop, not just at the end,
        allowing UIs to show running token counts.

        Args:
            input_tokens: Tokens sent to the model (context size).
            output_tokens: Tokens generated by the model (cumulative for session).
            usage: Full Usage object with extended details (cost, reasoning tokens, etc.).
                   May be None for providers that don't report extended details.
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
        require_finish: bool = False,
        validate_messages: bool = False,
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
            require_finish: Require agent to call Finish tool to complete.
            validate_messages: Validate message structure before API calls.
                Enable this in tests to catch message construction bugs.
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
        self._require_finish = require_finish

        # Track pending injections from hooks
        self._pending_injections: list[str] = []

        # Tool metrics collector
        self._metrics = tools_base.MetricsCollector()

        # Recovery tracking state
        self._recovery_count_session: int = 0
        self._recovery_count_turn: int = 0
        self._recent_recovered_hashes: set[str] = set()
        self._last_turn_had_recovery: bool = False

        # Finish tool tracking
        self._finish_called: bool = False
        self._finish_result: FinishResult | None = None
        self._finish_reminder_count: int = 0
        self._max_finish_reminders: int = 3

        # Message validation
        self._validate_messages = validate_messages

    def _check_message_invariants(
        self,
        messages: list[dict[str, _typing.Any]],
        context: str = "",  # noqa: ARG002
    ) -> None:
        """Validate message structure if validation is enabled.

        Args:
            messages: Messages to validate.
            context: Context string for error messages (for future use).

        Raises:
            MessageValidationError: If validation enabled and invariants violated.
        """
        if not self._validate_messages:
            return
        message_validators.validate_message_structure(messages, strict=True)

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
            result = self._make_success_result(tool_use, "[dry run - tool not executed]")
            # Still show the result to the UI
            result_display = core_types.ToolResultDisplay(
                tool_name=tool_use.name,
                result=result,
                tool_id=tool_use.id,
            )
            await self._callbacks.on_tool_result(result_display)
            return result

        # Check permission (skip for tools that don't require it)
        if tool.requires_permission:
            if self._auto_approve:
                pass  # Auto-approved
            elif not await self._callbacks.request_tool_permission(tool_call_display):
                result = self._make_error_result(tool_use, "Permission denied by user")
                # Still show the result to the UI
                result_display = core_types.ToolResultDisplay(
                    tool_name=tool_use.name,
                    result=result,
                    tool_id=tool_use.id,
                )
                await self._callbacks.on_tool_result(result_display)
                return result

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

    async def _handle_thinking_only_response(
        self,
        thinking: str,
        working_messages: list[dict[str, _typing.Any]],
    ) -> bool:
        """
        Handle a response that contained only thinking, no actual output.

        When the model produces thinking but no text or tool calls, we inject
        a fake tool error to prompt it to emit proper output.

        Args:
            thinking: The thinking content from the model
            working_messages: Message list to append feedback to

        Returns:
            True if we should continue the loop (retry), False to break
        """
        import uuid as _uuid

        max_thinking_retries = 3
        thinking_only_retries = getattr(self, "_thinking_only_retries", 0)

        if thinking and thinking_only_retries < max_thinking_retries:
            self._thinking_only_retries = thinking_only_retries + 1
            await self._callbacks.on_info(
                f"Model produced only thinking, no response. "
                f"Prompting to continue... (attempt {thinking_only_retries + 1}/{max_thinking_retries})"
            )
            if self._logger:
                # Log the full thinking content so it's visible in logs
                self._logger.log_event(
                    "thinking_only_response",
                    thinking=thinking,  # Full content, not just length
                    thinking_length=len(thinking),
                    retry_attempt=thinking_only_retries + 1,
                )

            # Add assistant message with fake tool call, then tool error response
            # This triggers the model's tool-calling behavior better than a user message
            # Include the thinking as reasoning so the model has context for the retry
            fake_tool_id = f"thinking-only-{_uuid.uuid4().hex[:8]}"
            assistant_feedback: dict[str, _typing.Any] = {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": fake_tool_id,
                    "type": "function",
                    "function": {
                        "name": "incomplete_response",
                        "arguments": "{}",
                    },
                }],
            }
            # Preserve the model's thinking so it has context for retry
            if thinking:
                assistant_feedback["reasoning"] = thinking
            # Use "tool_result" role (our internal format) - providers convert to "tool"
            error_feedback = {
                "role": "tool_result",
                "tool_use_id": fake_tool_id,
                "content": (
                    "ERROR: Your response contained only thinking/reasoning but you "
                    "did not actually emit a tool call. Your thinking mentioned wanting "
                    "to use tools, but no tool_calls were included in your response. "
                    "You MUST explicitly call a tool using the proper tool_calls format, "
                    "or provide a text response to the user. Try again."
                ),
                "is_error": True,
            }
            working_messages.append(assistant_feedback)
            working_messages.append(error_feedback)

            # Log the feedback injection so it's visible in logs
            if self._logger:
                self._logger.log_event(
                    "thinking_retry_feedback",
                    tool_call_id=fake_tool_id,
                    error_message=error_feedback["content"],
                )
            return True  # Continue loop

        # No thinking, or retry limit reached
        if thinking_only_retries >= max_thinking_retries:
            await self._callbacks.on_info(
                "Model failed to produce output after multiple attempts."
            )
        return False  # Break loop

    def _reset_thinking_only_retries(self) -> None:
        """Reset the thinking-only retry counter."""
        self._thinking_only_retries = 0

    def _check_for_finish(self, tool_use: api_types.ToolUse) -> bool:
        """Check if the tool use is a Finish call and record it.

        Args:
            tool_use: The tool use to check.

        Returns:
            True if this is a Finish call.
        """
        if tool_use.name == "Finish":
            self._finish_called = True
            self._finish_result = FinishResult(
                status=tool_use.input.get("status", "success"),
                summary=tool_use.input.get("summary", "Task completed."),
                next_steps=tool_use.input.get("next_steps"),
            )
            return True
        return False

    def _inject_finish_reminder(
        self, working_messages: list[dict[str, _typing.Any]]
    ) -> bool:
        """Inject a reminder to use the Finish tool.

        Args:
            working_messages: Message history to append to.

        Returns:
            True if reminder was injected, False if max reminders reached.
        """
        if self._finish_reminder_count >= self._max_finish_reminders:
            return False

        self._finish_reminder_count += 1
        working_messages.append({
            "role": "user",
            "content": (
                "You produced a text response but did not call the Finish tool. "
                "In require-finish mode, you must explicitly call "
                "Finish(status=..., summary=...) to signal task completion. "
                "Please call Finish now with an appropriate status and summary."
            ),
        })
        return True

    def _reset_finish_state(self) -> None:
        """Reset finish tracking state for a new turn."""
        self._finish_called = False
        self._finish_result = None
        self._finish_reminder_count = 0

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
                    finish_result=self._finish_result,
                )

            # Apply any pending injections before LLM call
            self._apply_pending_injections(working_messages)
            self._apply_recovery_feedback(working_messages)

            # Validate messages before API call
            self._check_message_invariants(
                working_messages, f"before streaming API call (round {tool_round})"
            )

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
                            finish_result=self._finish_result,
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

                    elif event.type == "message_delta":
                        # Usage info often comes in message_delta events
                        if event.usage:
                            usage = event.usage
                        if event.stop_reason:
                            stop_reason = event.stop_reason

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

            # Update totals and notify UI
            # NOTE: input_tokens is the ABSOLUTE context size for this call (not a delta)
            # Providers return the total prompt tokens sent, which IS the context size.
            # output_tokens is per-call generation, so we accumulate for session total.
            if usage:
                total_input = usage.input_tokens  # Last context size (not accumulated)
                total_output += usage.output_tokens
                await self._callbacks.on_usage_update(total_input, total_output, usage)

                # Log usage even if this turn only produced thinking
                if self._logger:
                    self._logger.log_usage(
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                        cost=usage.cost,
                        reasoning_tokens=usage.reasoning_tokens,
                        provider=usage.details.provider if usage.details else None,
                        generation_id=usage.details.generation_id if usage.details else None,
                    )
            else:
                # Log when provider doesn't report usage (unexpected)
                if self._logger:
                    self._logger.log_event(
                        "no_usage_reported",
                        message="Provider did not report usage for this API call",
                    )

            # If we have thinking that wasn't already shown (no text arrived), show it now
            # This handles: thinking → tool calls (no text in between)
            if current_thinking and not current_text:
                await self._callbacks.on_thinking_complete(current_thinking)

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

            # Try to recover tool calls from content [tool_call: ...] tags if still no tools
            # Some providers translate Harmony format into text tags instead of proper tool_calls
            if not tool_uses and current_text and self._tool_registry and self._can_recover_tool_call():
                recovery = tool_recovery.try_recover_tool_call_from_content(
                    current_text,
                    self._tool_registry,
                    model_recovery_enabled=True,  # Already checked in _can_recover
                )
                if recovery:
                    # Check for recovery loop
                    if self._is_recovery_loop(recovery.tool_use):
                        await self._callbacks.on_info(
                            f"Recovery loop detected: {recovery.tool_use.name} - stopping recovery"
                        )
                        if self._logger:
                            self._logger.log_event(
                                "recovery_loop_detected",
                                tool_name=recovery.tool_use.name,
                            )
                    elif recovery.requires_confirmation:
                        await self._callbacks.on_info(
                            f"Recovered tool call requires confirmation: {recovery.tool_use.name} "
                            f"(risk: {recovery.tool_risk_level})"
                        )
                    else:
                        tool_uses.append(recovery.tool_use)
                        self._record_recovery(recovery.tool_use)
                        await self._callbacks.on_info(
                            f"Recovered tool call from content: {recovery.tool_use.name} "
                            f"(type: {recovery.recovery_type})"
                        )
                    if self._logger:
                        self._logger.log_event(
                            "tool_call_recovered",
                            **recovery.to_log_dict(),
                        )

            # Handle response text and/or tool calls
            if tool_uses:
                # Clear loop detection hashes when native tool calls occur
                if not self._last_turn_had_recovery:
                    self._clear_recovery_hashes_on_native()
                # Model returned tool calls - add assistant message with tool_calls
                # This is required for OpenAI-compatible APIs to associate tool
                # results with the calls that generated them
                # Include thinking so the model remembers its reasoning
                working_messages.append(
                    core_types.format_assistant_tool_call(
                        tool_uses, current_text, thinking=current_thinking
                    )
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
                finish_detected = False
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
                            finish_result=self._finish_result,
                        )

                    # Check if this is a Finish tool call
                    if self._check_for_finish(tool_use):
                        finish_detected = True

                    tool_result = await self._execute_tool(tool_use)
                    all_tool_uses.append(tool_use)
                    all_tool_results.append(tool_result)

                    # Add tool result as individual message for next round
                    working_messages.append(
                        core_types.format_tool_result_message(tool_use.id, tool_result)
                    )

                    # If Finish was called, break out of tool loop
                    if finish_detected:
                        break

                # If Finish was called, break out of main loop
                if finish_detected:
                    final_response = current_text or self._finish_result.summary if self._finish_result else ""
                    break

            elif current_text:
                # No tool calls, just text response
                # In require_finish mode, we need the agent to call Finish
                if self._require_finish and not self._finish_called:
                    # Add assistant text to history first, then inject reminder
                    working_messages.append({"role": "assistant", "content": current_text})
                    await self._callbacks.on_text_complete(current_text, current_thinking)

                    # Log assistant response before continuing
                    if self._logger:
                        self._logger.log_assistant_message(
                            current_text,
                            thinking=current_thinking if current_thinking else None,
                        )

                    if self._inject_finish_reminder(working_messages):
                        continue  # Try again
                    else:
                        # Max reminders reached, accept implicit completion
                        pass

                # Normal completion - we're done
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
                # No text and no tool calls - model only produced thinking
                should_continue = await self._handle_thinking_only_response(
                    current_thinking, working_messages
                )
                if should_continue:
                    continue
                else:
                    break

        self._reset_thinking_only_retries()

        return ConversationResult(
            response_text=final_response,
            thinking=final_thinking,
            tool_uses=all_tool_uses,
            tool_results=all_tool_results,
            input_tokens=total_input,
            output_tokens=total_output,
            stop_reason=stop_reason if not self._finish_result else "finish",
            messages=working_messages,
            finish_result=self._finish_result,
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
                    finish_result=self._finish_result,
                )

            # Apply any pending injections before LLM call
            self._apply_pending_injections(working_messages)
            self._apply_recovery_feedback(working_messages)

            # Validate messages before API call
            self._check_message_invariants(
                working_messages, f"before complete API call (round {tool_round})"
            )

            # Make completion request
            response = await self._provider.complete(
                messages=working_messages,
                system=system_prompt,
                max_tokens=self._max_tokens,
                tools=tools,
            )

            # Update totals and notify UI
            # NOTE: input_tokens is the ABSOLUTE context size for this call (not a delta)
            # Providers return the total prompt tokens sent, which IS the context size.
            # output_tokens is per-call generation, so we accumulate for session total.
            if response.usage:
                total_input = response.usage.input_tokens  # Last context size (not accumulated)
                total_output += response.usage.output_tokens
                await self._callbacks.on_usage_update(total_input, total_output, response.usage)

                # Log usage
                if self._logger:
                    usage = response.usage
                    self._logger.log_usage(
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                        cost=usage.cost,
                        reasoning_tokens=usage.reasoning_tokens,
                        provider=usage.details.provider if usage.details else None,
                        generation_id=usage.details.generation_id if usage.details else None,
                    )
            else:
                # Log when provider doesn't report usage (unexpected)
                if self._logger:
                    self._logger.log_event(
                        "no_usage_reported",
                        message="Provider did not report usage for this API call",
                    )

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

            # Try to recover tool calls from content [tool_call: ...] tags if still no tools
            # Some providers translate Harmony format into text tags instead of proper tool_calls
            if (
                not tool_uses
                and response.content
                and self._tool_registry
                and self._can_recover_tool_call()
            ):
                recovery = tool_recovery.try_recover_tool_call_from_content(
                    response.content,
                    self._tool_registry,
                    model_recovery_enabled=True,  # Already checked in _can_recover
                )
                if recovery:
                    # Check for recovery loop
                    if self._is_recovery_loop(recovery.tool_use):
                        await self._callbacks.on_info(
                            f"Recovery loop detected: {recovery.tool_use.name} - stopping recovery"
                        )
                        if self._logger:
                            self._logger.log_event(
                                "recovery_loop_detected",
                                tool_name=recovery.tool_use.name,
                            )
                    elif recovery.requires_confirmation:
                        await self._callbacks.on_info(
                            f"Recovered tool call requires confirmation: {recovery.tool_use.name} "
                            f"(risk: {recovery.tool_risk_level})"
                        )
                    else:
                        tool_uses.append(recovery.tool_use)
                        self._record_recovery(recovery.tool_use)
                        await self._callbacks.on_info(
                            f"Recovered tool call from content: {recovery.tool_use.name} "
                            f"(type: {recovery.recovery_type})"
                        )
                    if self._logger:
                        self._logger.log_event(
                            "tool_call_recovered",
                            **recovery.to_log_dict(),
                        )

            # Handle response text and/or tool calls
            if tool_uses:
                # Clear loop detection hashes when native tool calls occur
                if not self._last_turn_had_recovery:
                    self._clear_recovery_hashes_on_native()
                # Model returned tool calls - add assistant message with tool_calls
                # This is required for OpenAI-compatible APIs to associate tool
                # results with the calls that generated them
                # Include thinking so the model remembers its reasoning
                working_messages.append(
                    core_types.format_assistant_tool_call(
                        tool_uses, response.content or "", thinking=response.thinking
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
                finish_detected = False
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
                            finish_result=self._finish_result,
                        )

                    # Check if this is a Finish tool call
                    if self._check_for_finish(tool_use):
                        finish_detected = True

                    tool_result = await self._execute_tool(tool_use)
                    all_tool_uses.append(tool_use)
                    all_tool_results.append(tool_result)

                    # Add tool result as individual message for next round
                    working_messages.append(
                        core_types.format_tool_result_message(tool_use.id, tool_result)
                    )

                    # If Finish was called, break out of tool loop
                    if finish_detected:
                        break

                # If Finish was called, break out of main loop
                if finish_detected:
                    final_response = response.content or self._finish_result.summary if self._finish_result else ""
                    break

            elif response.content:
                # No tool calls, just text response
                # In require_finish mode, we need the agent to call Finish
                if self._require_finish and not self._finish_called:
                    # Add assistant text to history first, then inject reminder
                    working_messages.append(
                        {"role": "assistant", "content": response.content}
                    )
                    await self._callbacks.on_text_complete(
                        response.content, response.thinking
                    )

                    # Log assistant response before continuing
                    if self._logger:
                        self._logger.log_assistant_message(
                            response.content,
                            thinking=response.thinking,
                        )

                    if self._inject_finish_reminder(working_messages):
                        continue  # Try again
                    else:
                        # Max reminders reached, accept implicit completion
                        pass

                # Normal completion - we're done
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
                # No text and no tool calls - model only produced thinking
                should_continue = await self._handle_thinking_only_response(
                    response.thinking or "", working_messages
                )
                if should_continue:
                    continue
                else:
                    break

        self._reset_thinking_only_retries()

        return ConversationResult(
            response_text=final_response,
            thinking=final_thinking,
            tool_uses=all_tool_uses,
            tool_results=all_tool_results,
            input_tokens=total_input,
            output_tokens=total_output,
            stop_reason=stop_reason if not self._finish_result else "finish",
            messages=working_messages,
            finish_result=self._finish_result,
        )

