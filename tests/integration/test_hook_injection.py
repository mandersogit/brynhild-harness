"""
Integration tests for hook inject_system_message.

Test IDs from design-plan-phase6.md:
- HI-01: Hook inject_system_message consumed
- HI-02: Stuck detection suggestion injected
- HI-03: Injection logged
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

    async def on_stream_start(self) -> None:
        pass

    async def on_stream_end(self) -> None:
        pass

    async def on_thinking_delta(self, text: str) -> None:  # noqa: ARG002
        pass

    async def on_thinking_complete(self, full_text: str) -> None:  # noqa: ARG002
        pass

    async def on_text_delta(self, text: str) -> None:  # noqa: ARG002
        pass

    async def on_text_complete(
        self,
        full_text: str,
        thinking: str | None,  # noqa: ARG002
    ) -> None:
        pass

    async def on_tool_call(self, tool_call: _typing.Any) -> None:  # noqa: ARG002
        pass

    async def request_tool_permission(
        self,
        tool_call: _typing.Any,  # noqa: ARG002
    ) -> bool:
        return True

    async def on_tool_result(self, result: _typing.Any) -> None:  # noqa: ARG002
        pass

    async def on_round_start(self, round_num: int) -> None:  # noqa: ARG002
        pass

    def is_cancelled(self) -> bool:
        return False


class MockProvider:
    """Mock LLM provider for testing."""

    _is_brynhild_duck_typed = True

    def __init__(self) -> None:
        self.name = "mock"
        self.model = "mock-model"

    def supports_tools(self) -> bool:
        return False


class TestHookInjectionIntegration:
    """Integration tests for hook inject_system_message."""

    @_pytest.mark.asyncio
    async def test_hi01_hook_inject_system_message_consumed(self) -> None:
        """HI-01: Hook returns inject, message appears in context."""
        # Create mock hook manager that returns inject_system_message
        mock_hook_manager = _mock.AsyncMock(spec=hooks_manager.HookManager)
        mock_hook_manager.dispatch.return_value = hooks_events.HookResult(
            action=hooks_events.HookAction.CONTINUE,
            inject_system_message="Important guidance from hook",
        )

        # Create mock tool registry
        mock_registry = _mock.MagicMock()
        mock_tool = _mock.AsyncMock()
        mock_tool.requires_permission = False
        mock_tool.execute.return_value = _mock.MagicMock(success=True, output="result", error=None)
        mock_registry.get.return_value = mock_tool

        # Create processor
        processor = conversation.ConversationProcessor(
            provider=MockProvider(),  # type: ignore
            callbacks=MockCallbacks(),
            tool_registry=mock_registry,
            hook_manager=mock_hook_manager,
        )

        # Execute tool (triggers hooks)
        tool_use = api_types.ToolUse(id="1", name="test_tool", input={})
        await processor._execute_tool(tool_use)

        # Verify injection was stored
        assert "Important guidance from hook" in processor._pending_injections

        # Verify it would be applied to messages
        messages: list[dict[str, _typing.Any]] = []
        processor._apply_pending_injections(messages)

        assert len(messages) == 1
        assert "Important guidance from hook" in messages[0]["content"]

    @_pytest.mark.asyncio
    async def test_hi02_stuck_detection_suggestion_injected(self) -> None:
        """HI-02: StuckDetector suggestion would be injected when stuck.

        Note: This tests the mechanism, not actual stuck detection.
        """
        # Create processor
        processor = conversation.ConversationProcessor(
            provider=MockProvider(),  # type: ignore
            callbacks=MockCallbacks(),
        )

        # Simulate stuck detection adding an injection
        stuck_suggestion = "Try a different approach: use grep instead of reading files."
        processor._pending_injections.append(stuck_suggestion)

        # Verify it would be applied
        messages: list[dict[str, _typing.Any]] = []
        processor._apply_pending_injections(messages)

        assert len(messages) == 1
        assert stuck_suggestion in messages[0]["content"]

    @_pytest.mark.asyncio
    async def test_hi03_injection_logged(self, tmp_path: _pathlib.Path) -> None:
        """HI-03: ConversationLogger records injected messages."""
        # Create logger
        log_file = tmp_path / "test.jsonl"
        logger = conversation_logger.ConversationLogger(
            log_file=log_file,
            provider="test",
            model="test-model",
            enabled=True,
        )

        # Create mock hook manager that returns inject_system_message
        mock_hook_manager = _mock.AsyncMock(spec=hooks_manager.HookManager)
        mock_hook_manager.dispatch.return_value = hooks_events.HookResult(
            action=hooks_events.HookAction.CONTINUE,
            inject_system_message="Logged hook injection",
        )

        # Create mock tool registry
        mock_registry = _mock.MagicMock()
        mock_tool = _mock.AsyncMock()
        mock_tool.requires_permission = False
        mock_tool.execute.return_value = _mock.MagicMock(success=True, output="result", error=None)
        mock_registry.get.return_value = mock_tool

        # Create processor with logger
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

        # Verify log contains injection
        log_content = log_file.read_text()
        assert "context_injection" in log_content
        assert '"source": "hook"' in log_content
        assert "Logged hook injection" in log_content


class TestInjectionMechanics:
    """Test the mechanics of injection application."""

    def test_multiple_injections_combined(self) -> None:
        """Multiple pending injections are combined into one message."""
        processor = conversation.ConversationProcessor(
            provider=MockProvider(),  # type: ignore
            callbacks=MockCallbacks(),
        )

        processor._pending_injections.append("First guidance")
        processor._pending_injections.append("Second guidance")
        processor._pending_injections.append("Third guidance")

        messages: list[dict[str, _typing.Any]] = []
        processor._apply_pending_injections(messages)

        # Should be one message
        assert len(messages) == 1
        # All content included
        assert "First guidance" in messages[0]["content"]
        assert "Second guidance" in messages[0]["content"]
        assert "Third guidance" in messages[0]["content"]

    def test_injections_cleared_after_application(self) -> None:
        """Pending injections are cleared after being applied."""
        processor = conversation.ConversationProcessor(
            provider=MockProvider(),  # type: ignore
            callbacks=MockCallbacks(),
        )

        processor._pending_injections.append("Some guidance")
        processor._apply_pending_injections([])

        # Should be empty now
        assert processor._pending_injections == []

    def test_no_injection_when_empty(self) -> None:
        """No message added when no pending injections."""
        processor = conversation.ConversationProcessor(
            provider=MockProvider(),  # type: ignore
            callbacks=MockCallbacks(),
        )

        messages: list[dict[str, _typing.Any]] = []
        processor._apply_pending_injections(messages)

        # No message should be added
        assert len(messages) == 0
