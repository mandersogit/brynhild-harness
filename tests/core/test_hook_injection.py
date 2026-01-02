"""
Tests for hook inject_system_message functionality in ConversationProcessor.

These tests verify that:
1. inject_system_message from pre_tool_use hooks is stored
2. inject_system_message from post_tool_use hooks is stored
3. Pending injections are applied before LLM calls
4. Injections are logged correctly
"""

import pathlib as _pathlib
import typing as _typing
import unittest.mock as _mock

import pytest as _pytest

import brynhild.api.types as api_types
import brynhild.core.conversation as conversation
import brynhild.hooks.events as hooks_events
import brynhild.hooks.manager as hooks_manager
import brynhild.logging.conversation_logger as conversation_logger


class MockCallbacks(conversation.ConversationCallbacks):
    """Mock callbacks for testing."""

    def __init__(self) -> None:
        self._cancelled = False

    async def on_stream_start(self) -> None:
        pass

    async def on_stream_end(self) -> None:
        pass

    async def on_thinking_delta(self, text: str) -> None:
        pass

    async def on_thinking_complete(self, full_text: str) -> None:
        pass

    async def on_text_delta(self, text: str) -> None:
        pass

    async def on_text_complete(self, full_text: str, thinking: str | None) -> None:
        pass

    async def on_tool_call(self, tool_call: _typing.Any) -> None:
        pass

    async def request_tool_permission(
        self,
        tool_call: _typing.Any,  # noqa: ARG002
    ) -> bool:
        return True

    async def on_tool_result(self, result: _typing.Any) -> None:
        pass

    async def on_round_start(self, round_num: int) -> None:
        pass

    def is_cancelled(self) -> bool:
        return self._cancelled


class MockProvider:
    """Mock LLM provider for testing."""

    def __init__(self) -> None:
        self.name = "mock"
        self.model = "mock-model"
        self.last_messages: list[dict[str, _typing.Any]] | None = None

    def supports_tools(self) -> bool:
        return False

    async def stream(
        self,
        messages: list[dict[str, _typing.Any]],
        system: str,  # noqa: ARG002
        max_tokens: int,  # noqa: ARG002
        tools: list[_typing.Any] | None = None,  # noqa: ARG002
    ) -> _typing.AsyncIterator[_typing.Any]:
        """Mock stream that captures messages."""
        self.last_messages = messages

        # Yield a simple response
        yield api_types.StreamEvent(
            type="text_delta",
            text="Response",
        )
        yield api_types.StreamEvent(
            type="content_stop",
            stop_reason="end_turn",
            usage=api_types.Usage(input_tokens=10, output_tokens=5),
        )


class TestPendingInjections:
    """Test pending injection storage and application."""

    def test_processor_starts_with_empty_pending_injections(self) -> None:
        """New processor has no pending injections."""
        processor = conversation.ConversationProcessor(
            provider=MockProvider(),  # type: ignore
            callbacks=MockCallbacks(),
        )

        assert processor._pending_injections == []

    def test_apply_pending_injections_adds_message(self) -> None:
        """Pending injections are added as messages."""
        processor = conversation.ConversationProcessor(
            provider=MockProvider(),  # type: ignore
            callbacks=MockCallbacks(),
        )

        # Add pending injection
        processor._pending_injections.append("Test guidance")

        # Apply to messages
        messages: list[dict[str, _typing.Any]] = []
        processor._apply_pending_injections(messages)

        # Should have added a message
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert "[System guidance]" in messages[0]["content"]
        assert "Test guidance" in messages[0]["content"]

    def test_apply_pending_injections_clears_list(self) -> None:
        """Applying injections clears the pending list."""
        processor = conversation.ConversationProcessor(
            provider=MockProvider(),  # type: ignore
            callbacks=MockCallbacks(),
        )

        processor._pending_injections.append("Test")
        processor._apply_pending_injections([])

        assert processor._pending_injections == []

    def test_apply_pending_injections_combines_multiple(self) -> None:
        """Multiple pending injections are combined."""
        processor = conversation.ConversationProcessor(
            provider=MockProvider(),  # type: ignore
            callbacks=MockCallbacks(),
        )

        processor._pending_injections.append("First guidance")
        processor._pending_injections.append("Second guidance")

        messages: list[dict[str, _typing.Any]] = []
        processor._apply_pending_injections(messages)

        # Should be combined in one message
        assert len(messages) == 1
        assert "First guidance" in messages[0]["content"]
        assert "Second guidance" in messages[0]["content"]

    def test_apply_pending_injections_no_op_when_empty(self) -> None:
        """No message added when no pending injections."""
        processor = conversation.ConversationProcessor(
            provider=MockProvider(),  # type: ignore
            callbacks=MockCallbacks(),
        )

        messages: list[dict[str, _typing.Any]] = []
        processor._apply_pending_injections(messages)

        assert len(messages) == 0


class TestHookInjectionIntegration:
    """Integration tests for hook-based injection."""

    @_pytest.mark.asyncio
    async def test_pre_tool_use_injection_stored(self) -> None:
        """inject_system_message from pre_tool_use is stored."""
        # Create mock hook manager
        mock_hook_manager = _mock.AsyncMock(spec=hooks_manager.HookManager)
        mock_hook_manager.dispatch.return_value = hooks_events.HookResult(
            action=hooks_events.HookAction.CONTINUE,
            inject_system_message="Pre-tool guidance",
        )

        # Create mock tool registry
        mock_registry = _mock.MagicMock()
        mock_tool = _mock.AsyncMock()
        mock_tool.requires_permission = False
        mock_tool.execute.return_value = _mock.MagicMock(success=True, output="result", error=None)
        mock_registry.get.return_value = mock_tool

        processor = conversation.ConversationProcessor(
            provider=MockProvider(),  # type: ignore
            callbacks=MockCallbacks(),
            tool_registry=mock_registry,
            hook_manager=mock_hook_manager,
        )

        # Execute tool
        tool_use = api_types.ToolUse(id="1", name="test_tool", input={})
        await processor._execute_tool(tool_use)

        # pre_tool_use hook was dispatched
        mock_hook_manager.dispatch.assert_called()

        # Injection should be stored
        assert "Pre-tool guidance" in processor._pending_injections

    @_pytest.mark.asyncio
    async def test_post_tool_use_injection_stored(self) -> None:
        """inject_system_message from post_tool_use is stored."""
        # Create mock hook manager that returns inject on post_tool_use
        mock_hook_manager = _mock.AsyncMock(spec=hooks_manager.HookManager)

        def dispatch_side_effect(
            event: hooks_events.HookEvent,
            ctx: _typing.Any,  # noqa: ARG001
        ) -> hooks_events.HookResult:
            if event == hooks_events.HookEvent.POST_TOOL_USE:
                return hooks_events.HookResult(
                    action=hooks_events.HookAction.CONTINUE,
                    inject_system_message="Post-tool guidance",
                )
            return hooks_events.HookResult(action=hooks_events.HookAction.CONTINUE)

        mock_hook_manager.dispatch.side_effect = dispatch_side_effect

        # Create mock tool registry
        mock_registry = _mock.MagicMock()
        mock_tool = _mock.AsyncMock()
        mock_tool.requires_permission = False
        mock_tool.execute.return_value = _mock.MagicMock(success=True, output="result", error=None)
        mock_registry.get.return_value = mock_tool

        processor = conversation.ConversationProcessor(
            provider=MockProvider(),  # type: ignore
            callbacks=MockCallbacks(),
            tool_registry=mock_registry,
            hook_manager=mock_hook_manager,
        )

        # Execute tool
        tool_use = api_types.ToolUse(id="1", name="test_tool", input={})
        await processor._execute_tool(tool_use)

        # Injection should be stored
        assert "Post-tool guidance" in processor._pending_injections


class TestInjectionLogging:
    """Test that injections are logged correctly."""

    @_pytest.mark.asyncio
    async def test_pre_tool_use_injection_logged(self, tmp_path: _pathlib.Path) -> None:
        """inject_system_message from pre_tool_use is logged."""
        log_file = tmp_path / "test.jsonl"
        logger = conversation_logger.ConversationLogger(
            log_file=log_file,
            provider="test",
            model="test-model",
            enabled=True,
        )

        # Create mock hook manager
        mock_hook_manager = _mock.AsyncMock(spec=hooks_manager.HookManager)
        mock_hook_manager.dispatch.return_value = hooks_events.HookResult(
            action=hooks_events.HookAction.CONTINUE,
            inject_system_message="Test guidance from hook",
        )

        # Create mock tool registry
        mock_registry = _mock.MagicMock()
        mock_tool = _mock.AsyncMock()
        mock_tool.requires_permission = False
        mock_tool.execute.return_value = _mock.MagicMock(success=True, output="result", error=None)
        mock_registry.get.return_value = mock_tool

        processor = conversation.ConversationProcessor(
            provider=MockProvider(),  # type: ignore
            callbacks=MockCallbacks(),
            tool_registry=mock_registry,
            hook_manager=mock_hook_manager,
            logger=logger,
        )

        # Execute tool
        tool_use = api_types.ToolUse(id="1", name="test_tool", input={})
        await processor._execute_tool(tool_use)

        logger.close()

        # Verify logging
        log_content = log_file.read_text()
        assert "context_injection" in log_content
        assert '"source": "hook"' in log_content
        assert "pre_tool_use" in log_content
