"""
Live tests for ConversationProcessor with real LLM providers.

These tests verify token tracking semantics against actual provider responses,
not mocks. They would catch bugs like token accumulation that mocks might miss.

Also tests real-time streaming token display integration.

Requirements:
    OPENROUTER_API_KEY: API key for OpenRouter
    or
    Ollama running locally

Run:
    pytest tests/live/test_live_conversation.py -v -m live
    pytest tests/live/test_live_conversation.py -v -m ollama_local
"""

import os as _os
import typing as _typing

import pytest as _pytest

import brynhild.api as api
import brynhild.core.conversation as conversation
import brynhild.core.types as core_types
import brynhild.tools.base as tools_base
import brynhild.tools.registry as tools_registry
import brynhild.ui.adapters as ui_adapters
import brynhild.ui.base as ui_base

pytestmark = [_pytest.mark.live, _pytest.mark.slow]


# =============================================================================
# Fixtures
# =============================================================================


@_pytest.fixture
def openrouter_provider() -> api.LLMProvider:
    """Create OpenRouter provider, skip if no API key."""
    api_key = _os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        _pytest.skip("OPENROUTER_API_KEY not set")

    model = _os.environ.get("BRYNHILD_TEST_MODEL", "openai/gpt-oss-20b")
    return api.create_provider(
        provider="openrouter",
        model=model,
        api_key=api_key,
    )


@_pytest.fixture
def ollama_provider() -> api.LLMProvider:
    """Create Ollama provider, skip if not available."""
    model = _os.environ.get("BRYNHILD_OLLAMA_MODEL", "qwen2.5:3b")
    try:
        provider = api.create_provider(provider="ollama", model=model)
        return provider
    except Exception as e:
        _pytest.skip(f"Ollama not available: {e}")


class CaptureCallbacks(conversation.ConversationCallbacks):
    """Callbacks that capture usage updates for verification."""

    def __init__(self) -> None:
        self.usage_updates: list[tuple[int, int]] = []
        self.usage_objects: list[_typing.Any] = []  # Full Usage objects for cost testing
        self.events: list[str] = []

    async def on_stream_start(self) -> None:
        self.events.append("stream_start")

    async def on_stream_end(self) -> None:
        self.events.append("stream_end")

    async def on_thinking_delta(self, text: str) -> None:
        pass

    async def on_thinking_complete(self, full_text: str) -> None:
        pass

    async def on_text_delta(self, text: str) -> None:
        pass

    async def on_text_complete(
        self,
        full_text: str,
        thinking: str | None,  # noqa: ARG002
    ) -> None:
        self.events.append(f"text_complete:{len(full_text)}")

    async def on_tool_call(self, tool_call: core_types.ToolCallDisplay) -> None:
        self.events.append(f"tool_call:{tool_call.tool_name}")

    async def request_tool_permission(
        self,
        tool_call: core_types.ToolCallDisplay,  # noqa: ARG002
    ) -> bool:
        return True  # Auto-approve for tests

    async def on_tool_result(self, result: core_types.ToolResultDisplay) -> None:
        self.events.append(f"tool_result:{result.tool_name}")

    async def on_round_start(self, round_num: int) -> None:
        self.events.append(f"round:{round_num}")

    def is_cancelled(self) -> bool:
        return False

    async def on_info(self, message: str) -> None:
        pass

    async def on_usage_update(
        self,
        input_tokens: int,
        output_tokens: int,
        usage: "_typing.Any | None" = None,
    ) -> None:
        self.usage_updates.append((input_tokens, output_tokens))
        # Store full usage for cost testing if available
        if usage is not None:
            self.usage_objects.append(usage)


class EchoTool(tools_base.Tool):
    """Simple tool that echoes input - for testing tool loops."""

    @property
    def name(self) -> str:
        return "Echo"

    @property
    def description(self) -> str:
        return "Echoes back the input. Use this when asked to echo something."

    @property
    def requires_permission(self) -> bool:
        return False

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to echo"},
            },
            "required": ["text"],
        }

    async def execute(self, input: dict) -> tools_base.ToolResult:
        return tools_base.ToolResult(
            success=True,
            output=f"Echo: {input.get('text', '')}",
            error=None,
        )


# =============================================================================
# Token Tracking Tests - These would catch the accumulation bug!
# =============================================================================


class TestLiveTokenTracking:
    """
    Live tests for token tracking semantics.

    These verify that ConversationProcessor correctly handles provider
    token reports as ABSOLUTE context sizes, not incremental deltas.
    """

    @_pytest.mark.asyncio
    @_pytest.mark.parametrize("provider_fixture", ["openrouter_provider"])
    async def test_token_values_are_reasonable(
        self, provider_fixture: str, request: _pytest.FixtureRequest
    ) -> None:
        """
        Basic sanity: tokens should be > 0 and input > output for short prompts.
        """
        provider = request.getfixturevalue(provider_fixture)
        callbacks = CaptureCallbacks()

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "Say 'hello' and nothing else."}],
            system_prompt="You are helpful.",
        )

        # Basic sanity checks
        assert result.input_tokens > 0, "Should have input tokens"
        assert result.output_tokens > 0, "Should have output tokens"

        # For a tiny prompt, input should be modest
        # Note: gpt-oss models have large Harmony-format system prompts (~1500+ tokens)
        assert result.input_tokens < 3000, (
            f"Input tokens {result.input_tokens} seems too high for tiny prompt"
        )

    @_pytest.mark.asyncio
    @_pytest.mark.parametrize("provider_fixture", ["openrouter_provider"])
    async def test_input_tokens_not_accumulated_with_tools(
        self, provider_fixture: str, request: _pytest.FixtureRequest
    ) -> None:
        """
        CRITICAL: With tool use, input_tokens should be final context size.

        This test would have caught the token accumulation bug.

        If provider makes 3 API calls with context sizes [500, 800, 1100],
        result.input_tokens should be ~1100, NOT ~2400 (sum).
        """
        provider = request.getfixturevalue(provider_fixture)
        if not provider.supports_tools():
            _pytest.skip("Provider doesn't support tools")

        callbacks = CaptureCallbacks()

        registry = tools_registry.ToolRegistry()
        registry.register(EchoTool())

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
        )

        result = await processor.process_streaming(
            messages=[
                {
                    "role": "user",
                    "content": "Use the Echo tool to echo 'test123', then say 'done'.",
                }
            ],
            system_prompt="You are helpful. When asked to echo, use the Echo tool.",
        )

        # If tool was called, we made multiple API calls
        tool_events = [e for e in callbacks.events if e.startswith("tool_call")]

        if tool_events:
            # With tool use, we had multiple API calls
            # Input tokens should be LAST context size, not accumulated
            #
            # Heuristic: if accumulated, input_tokens would be unreasonably high
            # A reasonable context for this tiny conversation is < 2000 tokens
            # If accumulating across 2-3 calls, we'd see 3000-6000+
            assert result.input_tokens < 3000, (
                f"input_tokens={result.input_tokens} seems too high. "
                f"With {len(tool_events)} tool calls, this may indicate "
                f"token accumulation bug. Expected < 3000 for small conversation."
            )

            # Also verify usage updates were received
            assert len(callbacks.usage_updates) > 0, "Should have usage updates"

            # Last usage update's input should match result
            last_input, _ = callbacks.usage_updates[-1]
            assert last_input == result.input_tokens, (
                f"Result input_tokens ({result.input_tokens}) should match "
                f"last callback update ({last_input})"
            )

    @_pytest.mark.asyncio
    @_pytest.mark.parametrize("provider_fixture", ["openrouter_provider"])
    async def test_output_tokens_accumulate(
        self, provider_fixture: str, request: _pytest.FixtureRequest
    ) -> None:
        """
        Output tokens SHOULD accumulate across API calls.

        With 3 API calls generating [50, 30, 40] tokens,
        result.output_tokens should be ~120 (sum).
        """
        provider = request.getfixturevalue(provider_fixture)
        if not provider.supports_tools():
            _pytest.skip("Provider doesn't support tools")

        callbacks = CaptureCallbacks()

        registry = tools_registry.ToolRegistry()
        registry.register(EchoTool())

        processor = conversation.ConversationProcessor(
            provider=provider,
            callbacks=callbacks,
            tool_registry=registry,
            auto_approve_tools=True,
        )

        await processor.process_streaming(
            messages=[
                {
                    "role": "user",
                    "content": "Echo 'a', then echo 'b', then say 'all done'.",
                }
            ],
            system_prompt="You are helpful. Use Echo tool when asked to echo.",
        )

        if len(callbacks.usage_updates) > 1:
            # With multiple API calls, output tokens should grow
            outputs = [out for _, out in callbacks.usage_updates]

            # Each update should show cumulative output (growing)
            for i in range(1, len(outputs)):
                assert outputs[i] >= outputs[i - 1], (
                    f"Output tokens should be cumulative. "
                    f"Got {outputs[i]} after {outputs[i-1]}"
                )


# =============================================================================
# Cost Tracking Tests (OpenRouter only)
# =============================================================================


class TestOpenRouterCostTracking:
    """Live tests for cost tracking from OpenRouter."""

    @_pytest.mark.asyncio
    async def test_openrouter_reports_cost(
        self, openrouter_provider: api.LLMProvider
    ) -> None:
        """OpenRouter should report cost in Usage.details."""
        callbacks = CaptureCallbacks()

        processor = conversation.ConversationProcessor(
            provider=openrouter_provider,
            callbacks=callbacks,
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "Say 'hi'."}],
            system_prompt="Be brief.",
        )

        # Should have captured at least one usage object
        assert len(callbacks.usage_objects) > 0, "Should have usage objects"

        # Check last usage object has cost details
        last_usage = callbacks.usage_objects[-1]
        assert hasattr(last_usage, "details"), "Usage should have details"
        assert last_usage.details is not None, "Details should not be None"
        assert last_usage.details.cost is not None, "Cost should be reported"
        assert last_usage.details.cost > 0, f"Cost should be > 0, got {last_usage.details.cost}"

        # Verify reasoning tokens breakdown (for reasoning models)
        if last_usage.details.reasoning_tokens is not None:
            assert last_usage.details.reasoning_tokens >= 0

    @_pytest.mark.asyncio
    async def test_cost_details_structure(
        self, openrouter_provider: api.LLMProvider
    ) -> None:
        """Verify the full structure of UsageDetails from OpenRouter."""
        callbacks = CaptureCallbacks()

        processor = conversation.ConversationProcessor(
            provider=openrouter_provider,
            callbacks=callbacks,
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "Hello"}],
            system_prompt="Respond briefly.",
        )

        assert len(callbacks.usage_objects) > 0
        last_usage = callbacks.usage_objects[-1]

        # Verify structure
        details = last_usage.details
        assert details is not None

        # Cost should be present
        assert details.cost is not None
        assert isinstance(details.cost, float)

        # Provider info should be present
        assert details.provider is not None, "Provider should be reported"
        assert len(details.provider) > 0

        # Generation ID should be present
        assert details.generation_id is not None, "Generation ID should be reported"
        assert details.generation_id.startswith("gen-")


# =============================================================================
# Ollama-specific tests (free to run)
# =============================================================================


@_pytest.mark.ollama_local
class TestOllamaTokenTracking:
    """Token tracking tests specifically for Ollama (free local provider)."""

    @_pytest.mark.asyncio
    async def test_ollama_tokens_reported(
        self, ollama_provider: api.LLMProvider
    ) -> None:
        """Ollama reports token usage through ConversationProcessor."""
        callbacks = CaptureCallbacks()

        processor = conversation.ConversationProcessor(
            provider=ollama_provider,
            callbacks=callbacks,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "Say 'hi'."}],
            system_prompt="Be brief.",
        )

        assert result.input_tokens > 0
        assert result.output_tokens > 0
        assert len(callbacks.usage_updates) > 0

    @_pytest.mark.asyncio
    async def test_ollama_multi_turn_tokens(
        self, ollama_provider: api.LLMProvider
    ) -> None:
        """
        Multi-turn conversation maintains reasonable token counts.

        Each turn's input_tokens should be larger than previous
        (context grows), but NOT by accumulated amounts.
        """
        callbacks1 = CaptureCallbacks()
        callbacks2 = CaptureCallbacks()

        # Turn 1
        processor1 = conversation.ConversationProcessor(
            provider=ollama_provider,
            callbacks=callbacks1,
        )

        result1 = await processor1.process_streaming(
            messages=[{"role": "user", "content": "Remember: X=42"}],
            system_prompt="Be brief.",
        )

        # Turn 2 (with history)
        processor2 = conversation.ConversationProcessor(
            provider=ollama_provider,
            callbacks=callbacks2,
        )

        messages = [
            {"role": "user", "content": "Remember: X=42"},
            {"role": "assistant", "content": result1.response_text},
            {"role": "user", "content": "What is X?"},
        ]

        result2 = await processor2.process_streaming(
            messages=messages,
            system_prompt="Be brief.",
        )

        # Turn 2 should have more input tokens (bigger context)
        assert result2.input_tokens > result1.input_tokens, (
            f"Turn 2 ({result2.input_tokens}) should have more context "
            f"than turn 1 ({result1.input_tokens})"
        )

        # But not ridiculously more (sanity check)
        growth = result2.input_tokens - result1.input_tokens
        assert growth < result1.input_tokens * 3, (
            f"Token growth {growth} seems excessive compared to "
            f"turn 1 size {result1.input_tokens}"
        )


# =============================================================================
# Real-Time Streaming Token Display Tests
# =============================================================================


class MockRendererForLiveTests(ui_base.Renderer):
    """
    Mock renderer that tracks streaming token display calls.
    """

    def __init__(self) -> None:
        self.streaming_mode_calls: list[bool] = []
        self.turn_token_updates: list[int] = []
        self.provider_token_updates: list[tuple[int, int]] = []

    def set_streaming_mode(self, is_streaming: bool) -> None:
        self.streaming_mode_calls.append(is_streaming)

    def update_turn_tokens(self, count: int) -> None:
        self.turn_token_updates.append(count)

    def update_token_counts(self, input_tokens: int, output_tokens: int) -> None:
        self.provider_token_updates.append((input_tokens, output_tokens))

    def start_streaming(self) -> None:
        pass

    def end_streaming(self) -> None:
        pass

    def show_user_message(self, content: str) -> None:
        pass

    def show_assistant_text(self, text: str, *, streaming: bool = False) -> None:
        pass

    def show_tool_call(self, tool_call: ui_base.ToolCallDisplay) -> None:
        pass

    def show_tool_result(self, result: ui_base.ToolResultDisplay) -> None:
        pass

    def show_error(self, error: str) -> None:
        pass

    def show_info(self, message: str) -> None:
        pass

    def prompt_permission(
        self,
        tool_call: ui_base.ToolCallDisplay,  # noqa: ARG002
        *,
        auto_approve: bool = False,
    ) -> bool:
        return auto_approve

    def finalize(self, result: dict[str, _typing.Any] | None = None) -> None:
        pass

    def show_finish(
        self,
        status: str,
        summary: str,
        next_steps: str | None = None,
    ) -> None:
        pass


@_pytest.mark.ollama_local
class TestOllamaStreamingTokenDisplay:
    """
    Live tests for real-time streaming token display with Ollama.

    Verifies:
    1. Client-side token counts increment during streaming
    2. Provider data replaces client estimates at turn end
    """

    @_pytest.mark.asyncio
    async def test_streaming_token_counts_increment(
        self, ollama_provider: api.LLMProvider
    ) -> None:
        """
        During streaming, token counts should increment.
        """
        renderer = MockRendererForLiveTests()
        callbacks = ui_adapters.RendererCallbacks(
            renderer,
            model=ollama_provider.model,
            auto_approve=True,
        )

        processor = conversation.ConversationProcessor(
            provider=ollama_provider,
            callbacks=callbacks,
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "Write a haiku about coding."}],
            system_prompt="You write poetry.",
        )

        # Should have received turn token updates during streaming
        assert len(renderer.turn_token_updates) > 0, (
            "Should have received turn token updates during streaming"
        )

        # Token counts should generally increase (may have some equal consecutive values)
        if len(renderer.turn_token_updates) > 1:
            # Last should be >= first
            assert renderer.turn_token_updates[-1] >= renderer.turn_token_updates[0], (
                "Token counts should accumulate during streaming"
            )

    @_pytest.mark.asyncio
    async def test_provider_data_received_at_end(
        self, ollama_provider: api.LLMProvider
    ) -> None:
        """
        Provider should report usage at turn end.
        """
        renderer = MockRendererForLiveTests()
        callbacks = ui_adapters.RendererCallbacks(
            renderer,
            model=ollama_provider.model,
            auto_approve=True,
        )

        processor = conversation.ConversationProcessor(
            provider=ollama_provider,
            callbacks=callbacks,
        )

        result = await processor.process_streaming(
            messages=[{"role": "user", "content": "Say hello."}],
            system_prompt="Be brief.",
        )

        # Provider should have reported usage
        assert len(renderer.provider_token_updates) > 0, (
            "Provider should report usage"
        )

        # Last provider update should match result
        last_input, last_output = renderer.provider_token_updates[-1]
        assert last_input == result.input_tokens
        # Output might be cumulative, check it's > 0
        assert last_output > 0

    @_pytest.mark.asyncio
    async def test_streaming_mode_toggled(
        self, ollama_provider: api.LLMProvider
    ) -> None:
        """
        Streaming mode should be set True at start, False at end.
        """
        renderer = MockRendererForLiveTests()
        callbacks = ui_adapters.RendererCallbacks(
            renderer,
            model=ollama_provider.model,
            auto_approve=True,
        )

        processor = conversation.ConversationProcessor(
            provider=ollama_provider,
            callbacks=callbacks,
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="Reply briefly.",
        )

        # Should have toggled streaming mode
        assert len(renderer.streaming_mode_calls) >= 2, (
            "Should have set streaming mode on and off"
        )
        assert renderer.streaming_mode_calls[0] is True, (
            "First streaming mode call should be True (start)"
        )
        assert renderer.streaming_mode_calls[-1] is False, (
            "Last streaming mode call should be False (end)"
        )

    @_pytest.mark.asyncio
    async def test_client_estimate_vs_provider_final(
        self, ollama_provider: api.LLMProvider
    ) -> None:
        """
        Client estimate during streaming should be non-zero and provider should report usage.

        CRITICAL: This test verifies the key invariant that provider data
        is authoritative. The client estimate is for UI feedback only.

        Note: Provider output_tokens may be MUCH higher than client estimate because:
        - Provider counts ALL tokens including thinking/reasoning
        - Client only counts tokens delivered via streaming callbacks
        - For reasoning models, thinking can be 5-10x the visible output
        """
        renderer = MockRendererForLiveTests()
        callbacks = ui_adapters.RendererCallbacks(
            renderer,
            model=ollama_provider.model,
            auto_approve=True,
        )

        processor = conversation.ConversationProcessor(
            provider=ollama_provider,
            callbacks=callbacks,
        )

        await processor.process_streaming(
            messages=[{"role": "user", "content": "Explain recursion in one sentence."}],
            system_prompt="Be concise.",
        )

        # Verify both client and provider produced counts
        assert len(renderer.turn_token_updates) > 0, "Should have client token updates"
        assert len(renderer.provider_token_updates) > 0, "Should have provider token updates"

        client_final = renderer.turn_token_updates[-1]
        _, provider_output = renderer.provider_token_updates[-1]

        # Client should have counted something
        assert client_final > 0, "Client should have counted tokens"
        # Provider should have reported output
        assert provider_output > 0, "Provider should report output tokens"

        # Provider output >= client estimate (provider may include thinking)
        # This is expected and correct - provider data is authoritative
        assert provider_output >= client_final * 0.5, (
            f"Provider output ({provider_output}) should be at least half of "
            f"client estimate ({client_final}) - something may be wrong"
        )

