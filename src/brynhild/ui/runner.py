"""
Conversation runner with tool execution loop.

This module provides a high-level interface for running conversations
with an LLM, using the shared ConversationProcessor for the core logic.
"""

import typing as _typing

import brynhild.api.base as api_base
import brynhild.constants as _constants

# Import core modules directly to avoid circular imports
import brynhild.core.conversation as core_conversation
import brynhild.core.prompts as core_prompts
import brynhild.logging as logging
import brynhild.tools.registry as tools_registry
import brynhild.ui.adapters as ui_adapters
import brynhild.ui.base as ui_base

# Re-export for convenience
get_system_prompt = core_prompts.get_system_prompt


class ConversationRunner:
    """
    Runs a conversation with tool execution support.

    This is a thin wrapper around ConversationProcessor that provides
    a simpler interface for non-interactive CLI use.
    """

    def __init__(
        self,
        provider: api_base.LLMProvider,
        renderer: ui_base.Renderer,
        *,
        tool_registry: tools_registry.ToolRegistry | None = None,
        max_tokens: int = _constants.DEFAULT_MAX_TOKENS,
        max_tool_rounds: int = _constants.DEFAULT_MAX_TOOL_ROUNDS,
        auto_approve_tools: bool = False,
        dry_run: bool = False,
        system_prompt: str | None = None,
        verbose: bool = False,
        logger: logging.ConversationLogger | None = None,
    ) -> None:
        """
        Initialize the conversation runner.

        Args:
            provider: LLM provider instance.
            renderer: UI renderer for output.
            tool_registry: Tool registry (uses default if not provided).
            max_tokens: Maximum tokens for LLM response.
            max_tool_rounds: Maximum rounds of tool execution.
            auto_approve_tools: Auto-approve all tool executions.
            dry_run: Show tool calls but don't execute them.
            system_prompt: System prompt (required).
            verbose: Log full API requests/responses for debugging.
            logger: Conversation logger for JSONL output.
        """
        self._provider = provider
        self._renderer = renderer
        if system_prompt is None:
            raise ValueError("system_prompt is required")
        self._system_prompt = system_prompt
        self._verbose = verbose
        self._logger = logger

        # Create callbacks for the renderer
        self._callbacks = ui_adapters.RendererCallbacks(
            renderer,
            auto_approve=auto_approve_tools,
            verbose=verbose,
        )

        # Create conversation processor
        self._processor = core_conversation.ConversationProcessor(
            provider=provider,
            callbacks=self._callbacks,
            tool_registry=tool_registry,
            max_tokens=max_tokens,
            max_tool_rounds=max_tool_rounds,
            auto_approve_tools=auto_approve_tools,
            dry_run=dry_run,
            logger=logger,
        )

        # Conversation state
        self._messages: list[dict[str, _typing.Any]] = []
        self._total_input_tokens = 0
        self._total_output_tokens = 0

        # Log system prompt at initialization
        if self._logger:
            self._logger.log_system_prompt(self._system_prompt)

    async def run_streaming(
        self,
        prompt: str,
    ) -> dict[str, _typing.Any]:
        """
        Run a conversation turn with streaming output.

        Args:
            prompt: User's message.

        Returns:
            Conversation result with response, usage, etc.
        """
        # Add user message
        self._messages.append({"role": "user", "content": prompt})

        # Log user message
        if self._logger:
            self._logger.log_user_message(prompt)

        # Process with streaming
        result = await self._processor.process_streaming(
            messages=self._messages,
            system_prompt=self._system_prompt,
        )

        # Update message history with assistant response
        if result.response_text:
            self._messages.append({"role": "assistant", "content": result.response_text})

        # Track usage
        self._total_input_tokens += result.input_tokens
        self._total_output_tokens += result.output_tokens

        # Build result dict for compatibility
        return {
            "response": result.response_text,
            "provider": self._provider.name,
            "model": self._provider.model,
            "stop_reason": result.stop_reason,
            "usage": {
                "input_tokens": self._total_input_tokens,
                "output_tokens": self._total_output_tokens,
                "total_tokens": self._total_input_tokens + self._total_output_tokens,
            },
        }

    async def run_complete(
        self,
        prompt: str,
    ) -> dict[str, _typing.Any]:
        """
        Run a conversation turn without streaming.

        Args:
            prompt: User's message.

        Returns:
            Conversation result with response, usage, etc.
        """
        # Add user message
        self._messages.append({"role": "user", "content": prompt})

        # Log user message
        if self._logger:
            self._logger.log_user_message(prompt)

        # Process without streaming
        result = await self._processor.process_complete(
            messages=self._messages,
            system_prompt=self._system_prompt,
        )

        # Update message history with assistant response
        if result.response_text:
            self._messages.append({"role": "assistant", "content": result.response_text})

        # Track usage
        self._total_input_tokens += result.input_tokens
        self._total_output_tokens += result.output_tokens

        # Build result dict for compatibility
        return {
            "response": result.response_text,
            "provider": self._provider.name,
            "model": self._provider.model,
            "stop_reason": result.stop_reason,
            "usage": {
                "input_tokens": self._total_input_tokens,
                "output_tokens": self._total_output_tokens,
                "total_tokens": self._total_input_tokens + self._total_output_tokens,
            },
        }

    def reset(self) -> None:
        """Reset conversation state for a new conversation."""
        self._messages = []
        self._total_input_tokens = 0
        self._total_output_tokens = 0
