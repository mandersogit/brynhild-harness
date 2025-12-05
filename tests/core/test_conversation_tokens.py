"""
Token tracking tests for ConversationProcessor.

These tests verify the semantic correctness of token values:
- input_tokens: Absolute context size (current API call), NOT accumulated
- output_tokens: Cumulative total generated across session

These tests exist because a token accounting bug shipped where input_tokens
were incorrectly accumulated instead of using absolute values.
"""

import typing as _typing

import pytest as _pytest

import brynhild.api.base as api_base
import brynhild.api.types as api_types
import brynhild.core.conversation as conversation
import brynhild.core.types as core_types
import brynhild.tools.base as tools_base
import brynhild.tools.registry as tools_registry

# =============================================================================
# Test Fixtures - Realistic Mock Provider
# =============================================================================


class RealisticUsageProvider(api_base.LLMProvider):
    """
    Mock provider that returns realistic GROWING context sizes.

    This reveals accumulation bugs that constant-value mocks hide.

    LLM providers return ABSOLUTE context size per call:
    - Call 1: 1000 tokens (system + user message)
    - Call 2: 2500 tokens (+ assistant + tool result)
    - Call 3: 4000 tokens (+ more messages)

    NOT incremental deltas.
    """

    def __init__(
        self,
        usage_sequence: list[tuple[int, int]],
        tool_calls_on: list[int] | None = None,
    ) -> None:
        """
        Initialize with a sequence of (input_tokens, output_tokens) per call.

        Args:
            usage_sequence: List of (input_tokens, output_tokens) tuples.
                           input_tokens should be GROWING (realistic context).
            tool_calls_on: List of call indices (0-based) that should return tool calls.
                          This creates multi-API-call scenarios.
        """
        self._usage_sequence = usage_sequence
        self._tool_calls_on = set(tool_calls_on or [])
        self._call_index = 0

    @property
    def name(self) -> str:
        return "realistic-mock"

    @property
    def model(self) -> str:
        return "realistic-mock-model"

    def supports_tools(self) -> bool:
        return True

    def supports_reasoning(self) -> bool:
        return False

    async def complete(
        self,
        messages: list[dict[str, _typing.Any]],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        tools: list[api_types.Tool] | None = None,
    ) -> api_types.CompletionResponse:
        # Collect from stream
        text_parts = []
        tool_uses = []
        usage = None

        async for event in self.stream(
            messages, system=system, max_tokens=max_tokens, tools=tools
        ):
            if event.type == "text_delta" and event.text:
                text_parts.append(event.text)
            elif event.type == "tool_use_start" and event.tool_use:
                tool_uses.append(event.tool_use)
            # Capture usage from message_delta event (how streaming works)
            elif event.type == "message_delta" and event.usage:
                usage = event.usage

        return api_types.CompletionResponse(
            id=f"call-{self._call_index}",
            content="".join(text_parts),
            stop_reason="tool_use" if tool_uses else "stop",
            usage=usage or api_types.Usage(input_tokens=0, output_tokens=0),
            tool_uses=tool_uses if tool_uses else None,
        )

    async def stream(
        self,
        messages: list[dict[str, _typing.Any]],  # noqa: ARG002
        *,
        system: str | None = None,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
        tools: list[api_types.Tool] | None = None,  # noqa: ARG002
    ) -> _typing.AsyncIterator[api_types.StreamEvent]:
        """Stream response with realistic usage values."""
        current_call = self._call_index

        # Get usage for this call
        if current_call < len(self._usage_sequence):
            input_tokens, output_tokens = self._usage_sequence[current_call]
        else:
            # Default if sequence exhausted
            input_tokens, output_tokens = 1000, 50

        # Emit response
        if current_call in self._tool_calls_on:
            yield api_types.StreamEvent(type="text_delta", text="Using tool...")
            yield api_types.StreamEvent(
                type="tool_use_start",
                tool_use=api_types.ToolUse(
                    id=f"tool-{current_call}",
                    name="MockTool",
                    input={"value": f"call-{current_call}"},
                ),
            )
            stop_reason = "tool_use"
        else:
            yield api_types.StreamEvent(
                type="text_delta", text=f"Response for call {current_call}"
            )
            stop_reason = "stop"

        # Usage comes in message_delta event (how real providers work)
        yield api_types.StreamEvent(
            type="message_delta",
            stop_reason=stop_reason,
            usage=api_types.Usage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            ),
        )

        self._call_index += 1


class CapturingCallbacks(conversation.ConversationCallbacks):
    """
    Callbacks that capture ALL events including on_usage_update.

    The standard MockCallbacks in test_conversation.py does NOT capture
    on_usage_update, which is why the token bug wasn't caught.
    """

    def __init__(self, grant_permission: bool = True) -> None:
        self.grant_permission = grant_permission
        self.events: list[tuple[str, _typing.Any]] = []
        self.usage_updates: list[tuple[int, int]] = []
        self._cancelled = False

    async def on_stream_start(self) -> None:
        self.events.append(("stream_start", None))

    async def on_stream_end(self) -> None:
        self.events.append(("stream_end", None))

    async def on_thinking_delta(self, text: str) -> None:
        self.events.append(("thinking_delta", text))

    async def on_thinking_complete(self, full_text: str) -> None:
        self.events.append(("thinking_complete", full_text))

    async def on_text_delta(self, text: str) -> None:
        self.events.append(("text_delta", text))

    async def on_text_complete(self, full_text: str, thinking: str | None) -> None:
        self.events.append(("text_complete", (full_text, thinking)))

    async def on_tool_call(self, tool_call: core_types.ToolCallDisplay) -> None:
        self.events.append(("tool_call", tool_call))

    async def request_tool_permission(
        self,
        tool_call: core_types.ToolCallDisplay,
    ) -> bool:
        self.events.append(("permission_request", tool_call))
        return self.grant_permission

    async def on_tool_result(self, result: core_types.ToolResultDisplay) -> None:
        self.events.append(("tool_result", result))

    async def on_round_start(self, round_num: int) -> None:
        self.events.append(("round_start", round_num))

    def is_cancelled(self) -> bool:
        return self._cancelled

    async def on_info(self, message: str) -> None:
        self.events.append(("info", message))

    async def on_usage_update(
        self,
        input_tokens: int,
        output_tokens: int,
        usage: "_typing.Any | None" = None,  # noqa: ARG002
    ) -> None:
        """Capture usage updates - this is the key callback for token tracking!"""
        self.usage_updates.append((input_tokens, output_tokens))
        self.events.append(("usage_update", (input_tokens, output_tokens)))


class MockToolForTokenTests(tools_base.Tool):
    """Simple mock tool for token tracking tests."""

    @property
    def name(self) -> str:
        return "MockTool"

    @property
    def description(self) -> str:
        return "Mock tool for testing"

    @property
    def requires_permission(self) -> bool:
        return False

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {
            "type": "object",
            "properties": {"value": {"type": "string"}},
        }

    async def execute(self, input: dict[str, _typing.Any]) -> tools_base.ToolResult:
        return tools_base.ToolResult(
            success=True,
            output=f"Executed with {input}",
            error=None,
        )


# =============================================================================
# Token Tracking Semantic Tests
# =============================================================================


class TestTokenTrackingSemantics:
    """
    Verify token values have correct semantics.

    The key insight: LLM providers return ABSOLUTE context size per call,
    not incremental deltas. Brynhild must not re-accumulate these.
    """

    @_pytest.mark.asyncio
    async def test_input_tokens_are_absolute_not_accumulated(self) -> None:
        """
        CRITICAL: input_tokens should be last API call's context size.

        This is the exact bug that was shipped and fixed.

        Setup:
        - Mock provider returns growing context sizes: [1000, 2500, 4000]
        - Simulate tool use loop (3 API calls)

        Expected:
        - result.input_tokens == 4000 (last value)
        - NOT 7500 (accumulated sum)
        """
        # Realistic growing context: each call's total context size
        usage_sequence = [
            (1000, 50),  # Call 1: initial context
            (2500, 100),  # Call 2: + assistant + tool result
            (4000, 150),  # Call 3: + more content
        ]

        provider = RealisticUsageProvider(
            usage_sequence=usage_sequence,
            tool_calls_on=[0, 1],  # First two calls return tool uses
        )

        registry = tools_registry.ToolRegistry()
        registry.register(MockToolForTokenTests())

        callbacks = CapturingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="You are helpful.",
        )

        # CRITICAL ASSERTION: input_tokens should be LAST context size, not sum
        assert result.input_tokens == 4000, (
            f"input_tokens should be last context size (4000), "
            f"got {result.input_tokens}. "
            f"If you got 7500, the accumulation bug is back!"
        )

    @_pytest.mark.asyncio
    async def test_output_tokens_are_accumulated(self) -> None:
        """
        output_tokens should be cumulative across session.

        Setup:
        - Mock provider returns: [50, 100, 150] output tokens per call
        - 3 API calls total

        Expected:
        - result.output_tokens == 300 (sum)
        """
        usage_sequence = [
            (1000, 50),
            (2000, 100),
            (3000, 150),
        ]

        provider = RealisticUsageProvider(
            usage_sequence=usage_sequence,
            tool_calls_on=[0, 1],
        )

        registry = tools_registry.ToolRegistry()
        registry.register(MockToolForTokenTests())

        callbacks = CapturingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="You are helpful.",
        )

        # Output tokens SHOULD be accumulated
        assert result.output_tokens == 300, (
            f"output_tokens should be accumulated sum (300), "
            f"got {result.output_tokens}"
        )

    @_pytest.mark.asyncio
    async def test_on_usage_update_receives_correct_values(self) -> None:
        """
        Callback should receive (absolute_context, cumulative_output).

        Setup:
        - Mock provider returns: [(1000, 50), (2500, 100), (4000, 150)]
        - Track all on_usage_update calls

        Expected callbacks:
        - Call 1: (1000, 50)
        - Call 2: (2500, 150)   # context=2500 (absolute), output=50+100
        - Call 3: (4000, 300)   # context=4000 (absolute), output=50+100+150
        """
        usage_sequence = [
            (1000, 50),
            (2500, 100),
            (4000, 150),
        ]

        provider = RealisticUsageProvider(
            usage_sequence=usage_sequence,
            tool_calls_on=[0, 1],
        )

        registry = tools_registry.ToolRegistry()
        registry.register(MockToolForTokenTests())

        callbacks = CapturingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="You are helpful.",
        )

        # Verify callback received correct values
        assert len(callbacks.usage_updates) == 3, (
            f"Expected 3 usage updates, got {len(callbacks.usage_updates)}"
        )

        # Each update should have (absolute_context, cumulative_output)
        expected = [
            (1000, 50),
            (2500, 150),  # 50 + 100
            (4000, 300),  # 50 + 100 + 150
        ]

        assert callbacks.usage_updates == expected, (
            f"Usage updates incorrect.\n"
            f"Expected: {expected}\n"
            f"Got: {callbacks.usage_updates}\n"
            f"If input_tokens are accumulated, the bug is back!"
        )


class TestTokenTrackingNonStreaming:
    """Same tests for non-streaming (complete) path."""

    @_pytest.mark.asyncio
    async def test_input_tokens_absolute_in_complete_mode(self) -> None:
        """
        Verify non-streaming path also uses absolute context size.
        """
        usage_sequence = [
            (1000, 50),
            (2500, 100),
            (4000, 150),
        ]

        provider = RealisticUsageProvider(
            usage_sequence=usage_sequence,
            tool_calls_on=[0, 1],
        )

        registry = tools_registry.ToolRegistry()
        registry.register(MockToolForTokenTests())

        callbacks = CapturingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
        )

        result = await processor.process_complete(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="You are helpful.",
        )

        assert result.input_tokens == 4000, (
            f"Non-streaming: input_tokens should be 4000, got {result.input_tokens}"
        )
        assert result.output_tokens == 300, (
            f"Non-streaming: output_tokens should be 300, got {result.output_tokens}"
        )


class ContentStopUsageProvider(api_base.LLMProvider):
    """
    Mock provider that sends usage via content_stop instead of message_delta.

    Some providers may do this - we need to handle both.
    """

    def __init__(self, input_tokens: int = 1000, output_tokens: int = 50) -> None:
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens

    @property
    def name(self) -> str:
        return "content-stop-mock"

    @property
    def model(self) -> str:
        return "content-stop-mock-model"

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
            id="content-stop-call",
            content="Response",
            stop_reason="stop",
            usage=api_types.Usage(
                input_tokens=self._input_tokens,
                output_tokens=self._output_tokens,
            ),
        )

    async def stream(
        self,
        messages: list[dict[str, _typing.Any]],  # noqa: ARG002
        *,
        system: str | None = None,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
        tools: list[api_types.Tool] | None = None,  # noqa: ARG002
    ) -> _typing.AsyncIterator[api_types.StreamEvent]:
        yield api_types.StreamEvent(type="text_delta", text="Response")
        # Send usage via content_stop, NOT message_delta
        yield api_types.StreamEvent(
            type="content_stop",
            stop_reason="stop",
            usage=api_types.Usage(
                input_tokens=self._input_tokens,
                output_tokens=self._output_tokens,
            ),
        )


class TestTokenTrackingEdgeCases:
    """Edge cases in token tracking."""

    @_pytest.mark.asyncio
    async def test_usage_from_content_stop_event(self) -> None:
        """
        Some providers send usage via content_stop, not message_delta.

        This tests the OTHER code path in conversation.py.
        """
        provider = ContentStopUsageProvider(input_tokens=3000, output_tokens=100)

        callbacks = CapturingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="You are helpful.",
        )

        # Usage should be captured from content_stop event
        assert result.input_tokens == 3000, (
            f"Expected 3000 from content_stop, got {result.input_tokens}"
        )
        assert result.output_tokens == 100

    @_pytest.mark.asyncio
    async def test_single_api_call_tokens_correct(self) -> None:
        """
        Single API call (no tool use) should report correct tokens.
        """
        provider = RealisticUsageProvider(
            usage_sequence=[(5000, 200)],
            tool_calls_on=[],  # No tool calls
        )

        callbacks = CapturingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="You are helpful.",
        )

        assert result.input_tokens == 5000
        assert result.output_tokens == 200

    @_pytest.mark.asyncio
    async def test_tokens_when_provider_returns_zero(self) -> None:
        """
        Provider returning 0 tokens should be handled gracefully.
        """
        provider = RealisticUsageProvider(
            usage_sequence=[(0, 0)],
            tool_calls_on=[],
        )

        callbacks = CapturingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="You are helpful.",
        )

        assert result.input_tokens == 0
        assert result.output_tokens == 0

    @_pytest.mark.asyncio
    async def test_many_tool_rounds_tokens_still_correct(self) -> None:
        """
        Even with many tool rounds, tokens should track correctly.

        This tests that the fix holds up under extended use.
        """
        # 5 tool rounds + final response = 6 API calls
        usage_sequence = [
            (1000, 20),
            (1500, 30),
            (2000, 40),
            (2500, 50),
            (3000, 60),
            (3500, 70),
        ]

        provider = RealisticUsageProvider(
            usage_sequence=usage_sequence,
            tool_calls_on=[0, 1, 2, 3, 4],  # Tool calls on first 5
        )

        registry = tools_registry.ToolRegistry()
        registry.register(MockToolForTokenTests())

        callbacks = CapturingCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
            max_tool_rounds=10,  # Allow many rounds
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="You are helpful.",
        )

        # Final context should be 3500 (last value)
        assert result.input_tokens == 3500, (
            f"After 6 calls, input_tokens should be 3500 (last), "
            f"got {result.input_tokens}. "
            f"Sum would be 13500 - if you see that, bug is back!"
        )

        # Output should be sum: 20+30+40+50+60+70 = 270
        assert result.output_tokens == 270

