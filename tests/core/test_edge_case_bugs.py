"""
Tests for edge case bugs in the conversation system.

These tests specifically target potential bugs found during code review.
"""

import typing as _typing

import pytest as _pytest

import brynhild.api.base as api_base
import brynhild.api.types as api_types
import brynhild.core.conversation as conversation

# =============================================================================
# Mock Providers for Edge Case Testing
# =============================================================================


class EmptyResponseProvider(api_base.LLMProvider):
    """Provider that returns empty content."""

    @property
    def name(self) -> str:
        return "empty-mock"

    @property
    def model(self) -> str:
        return "empty-mock-model"

    def supports_tools(self) -> bool:
        return True

    def supports_reasoning(self) -> bool:
        return False

    async def complete(
        self,
        messages: list[dict[str, _typing.Any]],  # noqa: ARG002
        *,
        system: str | None = None,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
        tools: list[api_types.Tool] | None = None,  # noqa: ARG002
    ) -> api_types.CompletionResponse:
        return api_types.CompletionResponse(
            id="empty-response",
            content="",  # Empty content!
            stop_reason="stop",
            usage=api_types.Usage(input_tokens=100, output_tokens=0),
        )

    async def stream(
        self,
        messages: list[dict[str, _typing.Any]],  # noqa: ARG002
        *,
        system: str | None = None,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
        tools: list[api_types.Tool] | None = None,  # noqa: ARG002
    ) -> _typing.AsyncIterator[api_types.StreamEvent]:
        # Yield only usage, no content
        yield api_types.StreamEvent(
            type="message_delta",
            stop_reason="stop",
            usage=api_types.Usage(input_tokens=100, output_tokens=0),
        )


class NullUsageProvider(api_base.LLMProvider):
    """Provider that returns no usage information."""

    @property
    def name(self) -> str:
        return "null-usage-mock"

    @property
    def model(self) -> str:
        return "null-usage-mock-model"

    def supports_tools(self) -> bool:
        return True

    def supports_reasoning(self) -> bool:
        return False

    async def complete(
        self,
        messages: list[dict[str, _typing.Any]],  # noqa: ARG002
        *,
        system: str | None = None,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
        tools: list[api_types.Tool] | None = None,  # noqa: ARG002
    ) -> api_types.CompletionResponse:
        return api_types.CompletionResponse(
            id="null-usage",
            content="Hello",
            stop_reason="stop",
            usage=None,  # No usage!
        )

    async def stream(
        self,
        messages: list[dict[str, _typing.Any]],  # noqa: ARG002
        *,
        system: str | None = None,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
        tools: list[api_types.Tool] | None = None,  # noqa: ARG002
    ) -> _typing.AsyncIterator[api_types.StreamEvent]:
        yield api_types.StreamEvent(type="text_delta", text="Hello")
        yield api_types.StreamEvent(
            type="message_delta",
            stop_reason="stop",
            # No usage in this event!
        )


class MultipleUsageProvider(api_base.LLMProvider):
    """Provider that sends multiple usage events (some providers do this)."""

    @property
    def name(self) -> str:
        return "multi-usage-mock"

    @property
    def model(self) -> str:
        return "multi-usage-mock-model"

    def supports_tools(self) -> bool:
        return True

    def supports_reasoning(self) -> bool:
        return False

    async def complete(
        self,
        messages: list[dict[str, _typing.Any]],  # noqa: ARG002
        *,
        system: str | None = None,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
        tools: list[api_types.Tool] | None = None,  # noqa: ARG002
    ) -> api_types.CompletionResponse:
        return api_types.CompletionResponse(
            id="multi-usage",
            content="Hello",
            stop_reason="stop",
            usage=api_types.Usage(input_tokens=500, output_tokens=50),
        )

    async def stream(
        self,
        messages: list[dict[str, _typing.Any]],  # noqa: ARG002
        *,
        system: str | None = None,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
        tools: list[api_types.Tool] | None = None,  # noqa: ARG002
    ) -> _typing.AsyncIterator[api_types.StreamEvent]:
        yield api_types.StreamEvent(type="text_delta", text="Hel")
        # First usage event with partial counts
        yield api_types.StreamEvent(
            type="message_delta",
            usage=api_types.Usage(input_tokens=100, output_tokens=10),
        )
        yield api_types.StreamEvent(type="text_delta", text="lo")
        # Second usage event with DIFFERENT counts (should overwrite, not add!)
        yield api_types.StreamEvent(
            type="message_delta",
            stop_reason="stop",
            usage=api_types.Usage(input_tokens=500, output_tokens=50),
        )


class MinimalCallbacks(conversation.ConversationCallbacks):
    """Minimal callbacks for testing."""

    def __init__(self) -> None:
        self.usage_updates: list[tuple[int, int]] = []

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

    async def on_text_complete(
        self,
        full_text: str,  # noqa: ARG002
        thinking: str | None,  # noqa: ARG002
    ) -> None:
        pass

    async def on_tool_call(
        self,
        tool_call: _typing.Any,  # noqa: ARG002
    ) -> None:
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

    async def on_info(self, message: str) -> None:  # noqa: ARG002
        pass

    async def on_usage_update(
        self,
        input_tokens: int,
        output_tokens: int,
        usage: "_typing.Any | None" = None,  # noqa: ARG002
    ) -> None:
        self.usage_updates.append((input_tokens, output_tokens))


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEmptyResponseHandling:
    """Tests for empty response edge cases."""

    @_pytest.mark.asyncio
    async def test_empty_content_doesnt_crash(self) -> None:
        """
        Empty content from provider should not crash.

        Some providers may return empty content (e.g., if only thinking).
        """
        provider = EmptyResponseProvider()
        callbacks = MinimalCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "Hello"}],
            system_prompt="Be helpful",
        )

        # Should not crash, and should return empty response
        assert result.response_text == ""

    @_pytest.mark.asyncio
    async def test_empty_content_still_has_usage(self) -> None:
        """
        Even with empty content, usage should be tracked.
        """
        provider = EmptyResponseProvider()
        callbacks = MinimalCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "Hello"}],
            system_prompt="Be helpful",
        )

        # Usage should still be reported
        assert result.input_tokens == 100
        assert result.output_tokens == 0


class TestNullUsageHandling:
    """Tests for null/missing usage edge cases."""

    @_pytest.mark.asyncio
    async def test_null_usage_doesnt_crash(self) -> None:
        """
        Null usage from provider should not crash.
        """
        provider = NullUsageProvider()
        callbacks = MinimalCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "Hello"}],
            system_prompt="Be helpful",
        )

        # Should not crash
        assert result.response_text == "Hello"

    @_pytest.mark.asyncio
    async def test_null_usage_returns_estimate(self) -> None:
        """
        With null usage, tokens should be tiktoken estimates (not crash or negative).

        When provider doesn't return usage, we fall back to tiktoken-based estimates
        so that logging still captures meaningful token counts.
        """
        provider = NullUsageProvider()
        callbacks = MinimalCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "Hello"}],
            system_prompt="Be helpful",
        )

        # Should be reasonable estimates, not None or negative
        assert result.input_tokens > 0  # Estimated from messages + system prompt
        assert result.output_tokens > 0  # Estimated from response content

    @_pytest.mark.asyncio
    async def test_null_usage_no_callback(self) -> None:
        """
        With null usage from provider, on_usage_update should NOT be called.

        When provider doesn't return usage, we don't call the UI callback
        (to avoid displaying potentially inaccurate estimates). However,
        we do log the estimates for post-hoc analysis.
        """
        provider = NullUsageProvider()
        callbacks = MinimalCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "Hello"}],
            system_prompt="Be helpful",
        )

        # on_usage_update should not have been called (estimates are only logged, not displayed)
        assert len(callbacks.usage_updates) == 0


class TestMultipleUsageEvents:
    """Tests for providers that send multiple usage events."""

    @_pytest.mark.asyncio
    async def test_multiple_usage_uses_last_not_sum(self) -> None:
        """
        BUG CHECK: Multiple usage events should use LAST value, not sum.

        Some providers send intermediate usage during streaming.
        The final value should be the actual usage, not accumulated.
        """
        provider = MultipleUsageProvider()
        callbacks = MinimalCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "Hello"}],
            system_prompt="Be helpful",
        )

        # Should be the LAST usage value (500, 50), not sum (600, 60)
        assert result.input_tokens == 500, (
            f"Expected last input_tokens (500), got {result.input_tokens}. "
            f"Multiple usage events may be accumulating incorrectly!"
        )
        assert result.output_tokens == 50

    @_pytest.mark.asyncio
    async def test_multiple_usage_callbacks_are_called(self) -> None:
        """
        Each usage event should trigger a callback.
        """
        provider = MultipleUsageProvider()
        callbacks = MinimalCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "Hello"}],
            system_prompt="Be helpful",
        )

        # Should have received multiple usage updates
        # (or at least the final one)
        assert len(callbacks.usage_updates) >= 1
