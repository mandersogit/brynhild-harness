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
import brynhild.skills as skills
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
        skill_registry: skills.SkillRegistry | None = None,
        max_tokens: int = _constants.DEFAULT_MAX_TOKENS,
        max_tool_rounds: int = _constants.DEFAULT_MAX_TOOL_ROUNDS,
        auto_approve_tools: bool = False,
        dry_run: bool = False,
        system_prompt: str | None = None,
        verbose: bool = False,
        logger: logging.ConversationLogger | None = None,
        markdown_logger: logging.MarkdownLogger | None = None,
        recovery_config: core_conversation.RecoveryConfig | None = None,
        show_thinking: bool = False,
        require_finish: bool = False,
    ) -> None:
        """
        Initialize the conversation runner.

        Args:
            provider: LLM provider instance.
            renderer: UI renderer for output.
            tool_registry: Tool registry (uses default if not provided).
            skill_registry: Skill registry for runtime skill triggering.
            max_tokens: Maximum tokens for LLM response.
            max_tool_rounds: Maximum rounds of tool execution.
            auto_approve_tools: Auto-approve all tool executions.
            dry_run: Show tool calls but don't execute them.
            system_prompt: System prompt (required).
            verbose: Log full API requests/responses for debugging.
            logger: Conversation logger for JSONL output.
            markdown_logger: Markdown logger for presentation output.
            recovery_config: Configuration for tool call recovery from thinking.
            show_thinking: If True, display full thinking/reasoning content.
            require_finish: Require agent to call Finish tool to complete.
        """
        self._provider = provider
        self._renderer = renderer
        self._skill_registry = skill_registry
        if system_prompt is None:
            raise ValueError("system_prompt is required")
        self._system_prompt = system_prompt
        self._verbose = verbose
        self._logger = logger
        self._markdown_logger = markdown_logger

        # Create callbacks for the renderer
        self._callbacks = ui_adapters.RendererCallbacks(
            renderer,
            auto_approve=auto_approve_tools,
            verbose=verbose,
            show_thinking=show_thinking,
            model=provider.model,  # For tiktoken encoder selection
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
            markdown_logger=markdown_logger,
            recovery_config=recovery_config,
            require_finish=require_finish,
        )

        # Conversation state
        self._messages: list[dict[str, _typing.Any]] = []
        # Token tracking:
        # - context tokens: absolute size (last API call), not accumulated
        # - output tokens: cumulative total generated across session
        self._current_context_tokens = 0
        self._total_output_tokens = 0

        # Log system prompt at initialization
        if self._logger:
            self._logger.log_system_prompt(self._system_prompt)

    def _preprocess_for_skills(self, prompt: str) -> tuple[str, str | None]:
        """
        Preprocess prompt for skill triggers.

        Args:
            prompt: Original user prompt.

        Returns:
            Tuple of (processed_prompt, skill_injection or None).
        """
        preprocess_result = skills.preprocess_for_skills(
            prompt,
            self._skill_registry,
        )

        # Handle skill errors
        if preprocess_result.error:
            self._renderer.show_info(f"Skill error: {preprocess_result.error}")

        # Log skill trigger if one was activated
        if preprocess_result.skill_injection and self._logger:
            self._logger.log_skill_triggered(
                skill_name=preprocess_result.skill_name or "unknown",
                skill_content=preprocess_result.skill_injection,
                trigger_type=preprocess_result.trigger_type or "explicit",
                trigger_match=prompt if preprocess_result.trigger_type == "explicit" else None,
            )

        # If skill was triggered, inject it as a message
        if preprocess_result.skill_injection:
            skill_message = skills.format_skill_injection_message(
                preprocess_result.skill_injection,
                preprocess_result.skill_name or "unknown",
            )
            self._messages.append({
                "role": "user",
                "content": f"[System: The following skill has been activated]\n\n{skill_message}",
            })
            if self._verbose:
                self._renderer.show_info(f"Skill '{preprocess_result.skill_name}' activated")

        # Return processed prompt
        user_message = preprocess_result.user_message
        if not user_message.strip() and preprocess_result.skill_injection:
            # Just the skill was injected, add minimal prompt
            user_message = "Please acknowledge the skill and wait for my request."

        return user_message, preprocess_result.skill_name

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
        # Preprocess for skill triggers
        user_message, triggered_skill = self._preprocess_for_skills(prompt)

        # Add user message
        self._messages.append({"role": "user", "content": user_message})

        # Log user message
        if self._logger:
            self._logger.log_user_message(user_message)

        # Process with streaming
        result = await self._processor.process_streaming(
            messages=self._messages,
            system_prompt=self._system_prompt,
        )

        # Update message history with assistant response
        if result.response_text:
            self._messages.append({"role": "assistant", "content": result.response_text})

        # Track usage (callback already notified renderer during conversation)
        # input_tokens is absolute context size (not accumulated)
        # output_tokens is cumulative across session
        self._current_context_tokens = result.input_tokens
        self._total_output_tokens += result.output_tokens

        # Display finish result if available
        if result.finish_result:
            self._renderer.show_finish(
                status=result.finish_result.status,
                summary=result.finish_result.summary,
                next_steps=result.finish_result.next_steps,
            )

        # Build result dict for compatibility
        result_dict: dict[str, _typing.Any] = {
            "response": result.response_text,
            "provider": self._provider.name,
            "model": self._provider.model,
            "stop_reason": result.stop_reason,
            "triggered_skill": triggered_skill,
            "usage": {
                "input_tokens": self._current_context_tokens,
                "output_tokens": self._total_output_tokens,
                "total_tokens": self._current_context_tokens + self._total_output_tokens,
            },
        }

        if result.finish_result:
            result_dict["finish"] = {
                "status": result.finish_result.status,
                "summary": result.finish_result.summary,
                "next_steps": result.finish_result.next_steps,
            }

        return result_dict

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
        # Preprocess for skill triggers
        user_message, triggered_skill = self._preprocess_for_skills(prompt)

        # Add user message
        self._messages.append({"role": "user", "content": user_message})

        # Log user message
        if self._logger:
            self._logger.log_user_message(user_message)

        # Process without streaming
        result = await self._processor.process_complete(
            messages=self._messages,
            system_prompt=self._system_prompt,
        )

        # Update message history with assistant response
        if result.response_text:
            self._messages.append({"role": "assistant", "content": result.response_text})

        # Track usage (callback already notified renderer during conversation)
        # input_tokens is absolute context size (not accumulated)
        # output_tokens is cumulative across session
        self._current_context_tokens = result.input_tokens
        self._total_output_tokens += result.output_tokens

        # Display finish result if available
        if result.finish_result:
            self._renderer.show_finish(
                status=result.finish_result.status,
                summary=result.finish_result.summary,
                next_steps=result.finish_result.next_steps,
            )

        # Build result dict for compatibility
        result_dict: dict[str, _typing.Any] = {
            "response": result.response_text,
            "provider": self._provider.name,
            "model": self._provider.model,
            "stop_reason": result.stop_reason,
            "usage": {
                "input_tokens": self._current_context_tokens,
                "output_tokens": self._total_output_tokens,
                "total_tokens": self._current_context_tokens + self._total_output_tokens,
            },
        }

        if result.finish_result:
            result_dict["finish"] = {
                "status": result.finish_result.status,
                "summary": result.finish_result.summary,
                "next_steps": result.finish_result.next_steps,
            }

        return result_dict

    def reset(self) -> None:
        """Reset conversation state for a new conversation."""
        self._messages = []
        self._current_context_tokens = 0
        self._total_output_tokens = 0
