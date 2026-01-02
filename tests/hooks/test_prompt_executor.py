"""Tests for prompt hook executor."""

import pathlib as _pathlib
import typing as _typing

import pytest as _pytest

import brynhild.api.types as api_types
import brynhild.hooks.config as config
import brynhild.hooks.events as events
import brynhild.hooks.executors.prompt as prompt_executor


class MockLLMProvider:
    """Mock LLM provider for testing prompt hooks."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.last_messages: list[dict[str, _typing.Any]] = []

    @property
    def name(self) -> str:
        return "mock"

    @property
    def model(self) -> str:
        return "mock-model"

    def supports_tools(self) -> bool:
        return False

    def supports_reasoning(self) -> bool:
        return False

    async def complete(
        self,
        messages: list[dict[str, _typing.Any]],
        **kwargs: _typing.Any,  # noqa: ARG002
    ) -> api_types.CompletionResponse:
        self.last_messages = messages
        return api_types.CompletionResponse(
            id="mock-id",
            content=self._response,
            stop_reason="stop",
            usage=api_types.Usage(input_tokens=10, output_tokens=5),
        )


class TestPromptHookExecutor:
    """Tests for PromptHookExecutor."""

    @_pytest.fixture
    def context(self, tmp_path: _pathlib.Path) -> events.HookContext:
        """Create a basic hook context."""
        return events.HookContext(
            event=events.HookEvent.PRE_TOOL_USE,
            session_id="test-session",
            cwd=tmp_path,
            tool="Bash",
            tool_input={"command": "rm -rf /"},
        )

    @_pytest.mark.asyncio
    async def test_safe_response_returns_continue(
        self,
        tmp_path: _pathlib.Path,
        context: events.HookContext,
    ) -> None:
        """LLM returning safe=true results in CONTINUE."""
        mock_provider = MockLLMProvider('{"safe": true, "reason": "Command is safe"}')
        executor = prompt_executor.PromptHookExecutor(
            project_root=tmp_path,
            provider=mock_provider,
        )

        hook_def = config.HookDefinition(
            name="safety-check",
            type="prompt",
            prompt="Is this command safe? {{tool_input.command}}",
        )

        result = await executor.execute(hook_def, context)
        assert result.action == events.HookAction.CONTINUE

    @_pytest.mark.asyncio
    async def test_unsafe_response_returns_block(
        self,
        tmp_path: _pathlib.Path,
        context: events.HookContext,
    ) -> None:
        """LLM returning safe=false results in BLOCK."""
        mock_provider = MockLLMProvider('{"safe": false, "reason": "Dangerous command"}')
        executor = prompt_executor.PromptHookExecutor(
            project_root=tmp_path,
            provider=mock_provider,
        )

        hook_def = config.HookDefinition(
            name="safety-check",
            type="prompt",
            prompt="Is this command safe? {{tool_input.command}}",
        )

        result = await executor.execute(hook_def, context)
        assert result.action == events.HookAction.BLOCK
        assert result.message is not None
        assert "Dangerous command" in result.message

    @_pytest.mark.asyncio
    async def test_action_based_response(
        self,
        tmp_path: _pathlib.Path,
        context: events.HookContext,
    ) -> None:
        """LLM returning action field is parsed correctly."""
        mock_provider = MockLLMProvider('{"action": "skip", "message": "Skip this one"}')
        executor = prompt_executor.PromptHookExecutor(
            project_root=tmp_path,
            provider=mock_provider,
        )

        hook_def = config.HookDefinition(
            name="review",
            type="prompt",
            prompt="Review: {{tool_input.command}}",
        )

        result = await executor.execute(hook_def, context)
        assert result.action == events.HookAction.SKIP
        assert result.message == "Skip this one"

    @_pytest.mark.asyncio
    async def test_no_json_returns_continue(
        self,
        tmp_path: _pathlib.Path,
        context: events.HookContext,
    ) -> None:
        """LLM returning text without JSON defaults to CONTINUE."""
        mock_provider = MockLLMProvider("I think this looks fine!")
        executor = prompt_executor.PromptHookExecutor(
            project_root=tmp_path,
            provider=mock_provider,
        )

        hook_def = config.HookDefinition(
            name="review",
            type="prompt",
            prompt="Review: {{tool_input.command}}",
        )

        result = await executor.execute(hook_def, context)
        assert result.action == events.HookAction.CONTINUE

    def test_no_prompt_raises_validation_error(self) -> None:
        """Hook without prompt field raises pydantic ValidationError."""
        import pydantic as _pydantic

        with _pytest.raises(_pydantic.ValidationError, match="prompt"):
            config.HookDefinition(
                name="no-prompt",
                type="prompt",
                # No prompt field - pydantic validates at creation
            )

    @_pytest.mark.asyncio
    async def test_template_rendering(
        self,
        tmp_path: _pathlib.Path,
        context: events.HookContext,
    ) -> None:
        """Prompt template variables are rendered correctly."""
        mock_provider = MockLLMProvider('{"safe": true}')
        executor = prompt_executor.PromptHookExecutor(
            project_root=tmp_path,
            provider=mock_provider,
        )

        hook_def = config.HookDefinition(
            name="template-test",
            type="prompt",
            prompt="Tool: {{tool}}, Command: {{tool_input.command}}",
        )

        await executor.execute(hook_def, context)

        # Check the rendered prompt was sent to the LLM
        assert len(mock_provider.last_messages) == 1
        sent_prompt = mock_provider.last_messages[0]["content"]
        assert "Tool: Bash" in sent_prompt
        assert "Command: rm -rf /" in sent_prompt
