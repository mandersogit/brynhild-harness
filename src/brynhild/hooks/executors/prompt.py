"""
Prompt hook executor - uses LLM for decisions.

Prompt hooks call an LLM to make decisions about whether to proceed.
The LLM is given a prompt template with context variables and must
respond with a JSON decision.

Example prompt:
    Review this bash command for safety:
    Command: {{tool_input.command}}

    Respond with JSON: {"safe": true/false, "reason": "..."}
"""

from __future__ import annotations

import json as _json
import re as _re
import typing as _typing

import brynhild.hooks.config as config
import brynhild.hooks.events as events
import brynhild.hooks.executors.base as base

if _typing.TYPE_CHECKING:
    import brynhild.api.base as api_base


class PromptHookExecutor(base.HookExecutor):
    """
    Executor for prompt hooks.

    Calls an LLM with a prompt template and parses the JSON response
    to determine the hook result.
    """

    def __init__(
        self,
        *,
        project_root: _typing.Any | None = None,
        provider: api_base.LLMProvider | None = None,
    ) -> None:
        """
        Initialize the prompt executor.

        Args:
            project_root: Project root directory.
            provider: LLM provider to use. If None, creates default provider.
        """
        super().__init__(project_root=project_root)
        self._provider = provider

    @property
    def hook_type(self) -> str:
        return "prompt"

    def _get_provider(self) -> api_base.LLMProvider:
        """Get or create the LLM provider."""
        if self._provider is None:
            import brynhild.api.factory as factory

            self._provider = factory.create_provider()
        return self._provider

    def _render_prompt(
        self,
        template: str,
        context: events.HookContext,
    ) -> str:
        """
        Render a prompt template with context variables.

        Supports {{variable}} and {{nested.variable}} syntax.
        """
        context_dict = context.to_dict()

        def replace_var(match: _re.Match[str]) -> str:
            var_path = match.group(1)
            parts = var_path.split(".")
            value: _typing.Any = context_dict
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part, "")
                else:
                    value = ""
                    break
            return str(value) if value is not None else ""

        return _re.sub(r"\{\{(\w+(?:\.\w+)*)\}\}", replace_var, template)

    async def _execute_impl(
        self,
        hook_def: config.HookDefinition,
        context: events.HookContext,
    ) -> events.HookResult:
        """
        Execute a prompt hook.

        Renders the prompt template, calls the LLM, and parses the
        JSON response.
        """
        prompt_template = hook_def.prompt
        if not prompt_template:
            raise base.HookExecutionError("Prompt hook has no prompt")

        # Render the prompt
        rendered_prompt = self._render_prompt(prompt_template, context)

        # Call the LLM
        provider = self._get_provider()
        response = await provider.complete(
            messages=[{"role": "user", "content": rendered_prompt}],
            max_tokens=500,  # Keep response short
        )

        # Parse the response
        return self._parse_response(response.content, hook_def.name)

    def _parse_response(
        self,
        response: str,
        hook_name: str,
    ) -> events.HookResult:
        """
        Parse LLM response to determine hook result.

        Looks for JSON in the response. Expected format:
        {"safe": true/false, "reason": "..."}
        or
        {"action": "continue|block|skip", "message": "..."}
        """
        # Try to extract JSON from response
        json_match = _re.search(r"\{[^{}]*\}", response)
        if not json_match:
            # No JSON found, assume continue
            return events.HookResult.continue_()

        try:
            data = _json.loads(json_match.group())
        except _json.JSONDecodeError:
            return events.HookResult.continue_()

        # Check for action-based response
        if "action" in data:
            return events.HookResult.from_dict(data)

        # Check for safe/unsafe response (common pattern)
        if "safe" in data:
            is_safe = data.get("safe", True)
            reason = data.get("reason", "")
            if is_safe:
                return events.HookResult.continue_()
            else:
                message = reason or f"Hook '{hook_name}' determined operation is unsafe"
                return events.HookResult.block(message)

        # Unknown format, continue
        return events.HookResult.continue_()

