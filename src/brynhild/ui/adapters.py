"""
UI callback adapters for core conversation processing.

These adapters bridge the core callback interfaces with UI implementations
(Renderer, async TUI methods, etc.).
"""

import typing as _typing

import brynhild.core.conversation as core_conversation
import brynhild.core.types as core_types
import brynhild.ui.base as ui_base
import brynhild.ui.tokenizer as tokenizer


class RendererCallbacks(core_conversation.ConversationCallbacks):
    """
    Callback adapter that wraps a synchronous Renderer.

    Used by ConversationRunner for non-interactive CLI mode.

    Implements ConversationCallbacks interface.

    Token counting:
        This class tracks per-turn output tokens during streaming using client-side
        tiktoken counting. These counts are TEMPORARY - they provide real-time
        feedback during streaming but are replaced by provider-reported values
        when the turn completes.
    """

    def __init__(
        self,
        renderer: ui_base.Renderer,
        *,
        auto_approve: bool = False,
        verbose: bool = False,
        show_thinking: bool = False,
        model: str = "gpt-4",
    ) -> None:
        self._renderer = renderer
        self._auto_approve = auto_approve
        self._verbose = verbose
        self._show_thinking = show_thinking
        self._thinking_shown = False
        self._thinking_stream_started = False  # Track if thinking Live is active
        self._content_started = False  # Track if real content has started
        self._accumulated_thinking = ""  # Accumulate thinking for full display
        # Token counting for streaming display
        self._turn_counter = tokenizer.TurnTokenCounter(model)
        self._is_streaming = False

    async def on_stream_start(self) -> None:
        self._renderer.start_streaming()
        self._thinking_shown = False
        self._thinking_stream_started = False
        self._content_started = False
        self._accumulated_thinking = ""
        # Reset turn token counter for new turn
        self._turn_counter.reset()
        self._is_streaming = True
        # Set renderer to streaming mode for footer display
        if hasattr(self._renderer, "set_streaming_mode"):
            self._renderer.set_streaming_mode(True)

    async def on_stream_end(self) -> None:
        self._is_streaming = False
        # Switch renderer back to non-streaming mode for footer display
        if hasattr(self._renderer, "set_streaming_mode"):
            self._renderer.set_streaming_mode(False)
        self._renderer.end_streaming()

    async def on_thinking_delta(self, text: str) -> None:
        # Accumulate thinking
        self._accumulated_thinking += text

        # Count tokens for streaming display
        turn_tokens = self._turn_counter.add_text(text)
        if hasattr(self._renderer, "update_turn_tokens"):
            self._renderer.update_turn_tokens(turn_tokens)

        # Start/update thinking stream (always show activity)
        if hasattr(self._renderer, "start_thinking_stream"):
            if not self._thinking_stream_started:
                self._renderer.start_thinking_stream()
                self._thinking_stream_started = True
            if hasattr(self._renderer, "update_thinking_stream"):
                self._renderer.update_thinking_stream(text)

    async def on_thinking_complete(self, full_text: str) -> None:
        # End the thinking stream
        if self._thinking_stream_started and hasattr(self._renderer, "end_thinking_stream"):
            # Persist the panel if --show-thinking is enabled
            self._renderer.end_thinking_stream(persist=self._show_thinking)
            self._thinking_stream_started = False
        elif self._show_thinking:
            # Fallback for renderers without streaming - show full panel
            if hasattr(self._renderer, "show_thinking"):
                self._renderer.show_thinking(full_text)
            else:
                self._renderer.show_info(f"💭 Thinking:\n{full_text}")

        # Always show summary if not persisting
        if not self._show_thinking:
            word_count = len(full_text.split())
            self._renderer.show_info(f"💭 [Thinking: {word_count} words]")

        self._thinking_shown = True

    async def on_text_delta(self, text: str) -> None:
        # Skip leading whitespace - models often send '\n\n' before tool calls
        # This prevents empty "Assistant" boxes from appearing
        if not self._content_started:
            if not text.strip():
                return  # Skip whitespace-only content
            self._content_started = True

        # Count tokens for streaming display
        turn_tokens = self._turn_counter.add_text(text)
        if hasattr(self._renderer, "update_turn_tokens"):
            self._renderer.update_turn_tokens(turn_tokens)

        self._renderer.show_assistant_text(text, streaming=True)

    async def on_text_complete(
        self,
        full_text: str,  # noqa: ARG002
        thinking: str | None,  # noqa: ARG002
    ) -> None:
        # Text is already shown via deltas
        pass

    async def on_tool_call(self, tool_call: core_types.ToolCallDisplay) -> None:
        self._renderer.show_tool_call(tool_call)

    async def request_tool_permission(
        self,
        tool_call: core_types.ToolCallDisplay,
    ) -> bool:
        if self._auto_approve:
            return True
        return self._renderer.prompt_permission(tool_call, auto_approve=False)

    async def on_tool_result(self, result: core_types.ToolResultDisplay) -> None:
        self._renderer.show_tool_result(result)

    async def on_round_start(self, round_num: int) -> None:
        if self._verbose:
            self._renderer.show_info(f"[Round {round_num}]")

    def is_cancelled(self) -> bool:
        return False

    async def on_info(self, message: str) -> None:
        self._renderer.show_info(message)

    async def on_usage_update(
        self,
        input_tokens: int,
        output_tokens: int,
        usage: "_typing.Any | None" = None,
    ) -> None:
        """Update renderer's token counts and cost for panel footers."""
        if hasattr(self._renderer, "update_token_counts"):
            self._renderer.update_token_counts(input_tokens, output_tokens)
        # Update cost if the renderer supports it and usage has details
        if hasattr(self._renderer, "update_cost") and usage is not None:  # noqa: SIM102
            if hasattr(usage, "details") and usage.details is not None:
                self._renderer.update_cost(
                    usage.details.cost,
                    usage.details.reasoning_tokens,
                )


class SyncCallbackAdapter:
    """
    Adapter that wraps a synchronous Renderer as async callbacks.

    Used by ConversationRunner which uses synchronous renderers.

    Implements ToolExecutionCallbacks interface.
    """

    def __init__(
        self,
        renderer: ui_base.Renderer,
        *,
        auto_approve: bool = False,
    ) -> None:
        self._renderer = renderer
        self._auto_approve = auto_approve

    async def show_tool_call(self, tool_call: core_types.ToolCallDisplay) -> None:
        self._renderer.show_tool_call(tool_call)

    async def request_permission(
        self,
        tool_call: core_types.ToolCallDisplay,
        *,
        auto_approve: bool = False,
    ) -> bool:
        # Use instance default if not overridden
        effective_auto_approve = auto_approve or self._auto_approve
        return self._renderer.prompt_permission(
            tool_call,
            auto_approve=effective_auto_approve,
        )

    async def show_tool_result(self, result: core_types.ToolResultDisplay) -> None:
        self._renderer.show_tool_result(result)


class AsyncCallbackAdapter:
    """
    Adapter that wraps async callback functions.

    Used by BrynhildApp (TUI) which uses async methods for display and permission.

    Implements ToolExecutionCallbacks interface.
    """

    def __init__(
        self,
        show_tool_call_fn: _typing.Callable[
            [core_types.ToolCallDisplay], _typing.Awaitable[None]
        ],
        request_permission_fn: _typing.Callable[
            [core_types.ToolCallDisplay], _typing.Awaitable[bool]
        ],
        show_tool_result_fn: _typing.Callable[
            [core_types.ToolResultDisplay], _typing.Awaitable[None]
        ]
        | None = None,
    ) -> None:
        """
        Initialize with async callback functions.

        Args:
            show_tool_call_fn: Async function to display a tool call.
            request_permission_fn: Async function to request permission.
            show_tool_result_fn: Optional async function to display tool result.
        """
        self._show_tool_call_fn = show_tool_call_fn
        self._request_permission_fn = request_permission_fn
        self._show_tool_result_fn = show_tool_result_fn

    async def show_tool_call(self, tool_call: core_types.ToolCallDisplay) -> None:
        await self._show_tool_call_fn(tool_call)

    async def request_permission(
        self,
        tool_call: core_types.ToolCallDisplay,
        *,
        auto_approve: bool = False,  # noqa: ARG002 - ignored, controlled by fn
    ) -> bool:
        return await self._request_permission_fn(tool_call)

    async def show_tool_result(self, result: core_types.ToolResultDisplay) -> None:
        if self._show_tool_result_fn:
            await self._show_tool_result_fn(result)

