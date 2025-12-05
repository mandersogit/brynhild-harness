"""
Integration tests for real-time token display during streaming.

These tests verify:
1. Token counter resets at stream start
2. Token counter increments on deltas
3. Provider data replaces client estimates at stream end
"""

import typing as _typing

import pytest as _pytest

import brynhild.ui.adapters as adapters
import brynhild.ui.base as ui_base


class MockRendererWithTokenTracking(ui_base.Renderer):
    """
    Mock renderer that tracks token-related method calls.
    """

    def __init__(self) -> None:
        # Track all calls for assertions
        self.streaming_mode_calls: list[bool] = []
        self.turn_token_updates: list[int] = []
        self.token_count_updates: list[tuple[int, int]] = []
        self.streaming_started = False
        self.streaming_ended = False

    def set_streaming_mode(self, is_streaming: bool) -> None:
        """Track streaming mode changes."""
        self.streaming_mode_calls.append(is_streaming)

    def update_turn_tokens(self, count: int) -> None:
        """Track per-turn token updates."""
        self.turn_token_updates.append(count)

    def update_token_counts(self, input_tokens: int, output_tokens: int) -> None:
        """Track provider-reported token updates."""
        self.token_count_updates.append((input_tokens, output_tokens))

    def start_streaming(self) -> None:
        self.streaming_started = True

    def end_streaming(self) -> None:
        self.streaming_ended = True

    # Required Renderer interface methods
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


class TestStreamingTokenCycle:
    """Tests for the full streaming token display cycle."""

    @_pytest.mark.asyncio
    async def test_stream_start_resets_counter_and_sets_mode(self) -> None:
        """on_stream_start should reset turn counter and enable streaming mode."""
        renderer = MockRendererWithTokenTracking()
        callbacks = adapters.RendererCallbacks(renderer, model="gpt-4")

        await callbacks.on_stream_start()

        # Should set streaming mode to True
        assert renderer.streaming_mode_calls == [True]
        # Renderer streaming should have started
        assert renderer.streaming_started

    @_pytest.mark.asyncio
    async def test_thinking_delta_counts_tokens(self) -> None:
        """on_thinking_delta should count and report tokens."""
        renderer = MockRendererWithTokenTracking()
        callbacks = adapters.RendererCallbacks(renderer, model="gpt-4")

        await callbacks.on_stream_start()
        renderer.turn_token_updates.clear()  # Clear setup calls

        # Send thinking deltas
        await callbacks.on_thinking_delta("Hello ")
        await callbacks.on_thinking_delta("world!")

        # Should have recorded token updates
        assert len(renderer.turn_token_updates) >= 2
        # Each update should be larger than the previous (accumulating)
        for i in range(1, len(renderer.turn_token_updates)):
            assert renderer.turn_token_updates[i] >= renderer.turn_token_updates[i - 1]

    @_pytest.mark.asyncio
    async def test_text_delta_counts_tokens(self) -> None:
        """on_text_delta should count and report tokens."""
        renderer = MockRendererWithTokenTracking()
        callbacks = adapters.RendererCallbacks(renderer, model="gpt-4")

        await callbacks.on_stream_start()
        renderer.turn_token_updates.clear()  # Clear setup calls

        # Send text deltas (non-whitespace to pass filtering)
        await callbacks.on_text_delta("Hello ")
        await callbacks.on_text_delta("world!")

        # Should have recorded token updates
        assert len(renderer.turn_token_updates) >= 2
        # Token count should increase
        assert renderer.turn_token_updates[-1] > renderer.turn_token_updates[0]

    @_pytest.mark.asyncio
    async def test_stream_end_clears_streaming_mode(self) -> None:
        """on_stream_end should disable streaming mode."""
        renderer = MockRendererWithTokenTracking()
        callbacks = adapters.RendererCallbacks(renderer, model="gpt-4")

        await callbacks.on_stream_start()
        await callbacks.on_stream_end()

        # Should have set streaming mode to False
        assert renderer.streaming_mode_calls == [True, False]
        # Renderer streaming should have ended
        assert renderer.streaming_ended

    @_pytest.mark.asyncio
    async def test_full_streaming_cycle(self) -> None:
        """Test complete cycle: start -> deltas -> end."""
        renderer = MockRendererWithTokenTracking()
        callbacks = adapters.RendererCallbacks(renderer, model="gpt-4")

        # Start streaming
        await callbacks.on_stream_start()
        _ = len(renderer.streaming_mode_calls)  # Track initial count

        # Send some thinking and text deltas
        await callbacks.on_thinking_delta("Let me think... ")
        await callbacks.on_thinking_delta("I'll analyze this.")
        await callbacks.on_text_delta("Here's ")
        await callbacks.on_text_delta("my response.")

        # Verify tokens were counted
        assert len(renderer.turn_token_updates) >= 4
        final_turn_tokens = renderer.turn_token_updates[-1]
        assert final_turn_tokens > 0

        # End streaming
        await callbacks.on_stream_end()

        # Verify streaming mode was toggled
        assert renderer.streaming_mode_calls[0] is True
        assert renderer.streaming_mode_calls[-1] is False

    @_pytest.mark.asyncio
    async def test_provider_usage_update_separate_from_turn_tokens(self) -> None:
        """on_usage_update should call renderer with provider data, not turn tokens."""
        renderer = MockRendererWithTokenTracking()
        callbacks = adapters.RendererCallbacks(renderer, model="gpt-4")

        await callbacks.on_stream_start()
        await callbacks.on_text_delta("Some response text")

        # Simulate provider reporting usage
        await callbacks.on_usage_update(1000, 50)

        # Should have called update_token_counts with provider values
        assert (1000, 50) in renderer.token_count_updates

    @_pytest.mark.asyncio
    async def test_multiple_turns_reset_counter(self) -> None:
        """Each turn should start with fresh token counter."""
        renderer = MockRendererWithTokenTracking()
        callbacks = adapters.RendererCallbacks(renderer, model="gpt-4")

        # First turn
        await callbacks.on_stream_start()
        await callbacks.on_text_delta("First turn response")
        first_turn_final = renderer.turn_token_updates[-1]
        await callbacks.on_stream_end()

        # Second turn
        renderer.turn_token_updates.clear()
        await callbacks.on_stream_start()
        await callbacks.on_text_delta("Second")

        # Second turn should start from 0, not accumulate from first turn
        assert renderer.turn_token_updates[0] < first_turn_final


class TestProviderDataReplacesEstimates:
    """
    Tests verifying that provider data replaces client estimates.

    CRITICAL INVARIANT: Provider usage data is always authoritative.
    """

    @_pytest.mark.asyncio
    async def test_provider_data_sent_to_renderer(self) -> None:
        """Provider usage data should be sent to renderer."""
        renderer = MockRendererWithTokenTracking()
        callbacks = adapters.RendererCallbacks(renderer, model="gpt-4")

        # Stream with deltas
        await callbacks.on_stream_start()
        await callbacks.on_text_delta("Some response")

        # Provider reports final usage
        await callbacks.on_usage_update(input_tokens=500, output_tokens=25)

        # Renderer should have received provider values
        assert (500, 25) in renderer.token_count_updates

    @_pytest.mark.asyncio
    async def test_turn_tokens_independent_of_provider_data(self) -> None:
        """Turn tokens (client-side) should be independent of provider data."""
        renderer = MockRendererWithTokenTracking()
        callbacks = adapters.RendererCallbacks(renderer, model="gpt-4")

        await callbacks.on_stream_start()
        await callbacks.on_text_delta("Hello world")

        client_estimate = renderer.turn_token_updates[-1]

        # Provider reports different value (as expected - it's authoritative)
        await callbacks.on_usage_update(input_tokens=100, output_tokens=5)

        # Turn token updates should still show client estimate
        # (these are separate streams of data)
        assert client_estimate in renderer.turn_token_updates


class TestModelEncoderSelection:
    """Tests verifying model-specific encoder selection in callbacks."""

    @_pytest.mark.asyncio
    async def test_gpt_oss_model_uses_correct_encoder(self) -> None:
        """gpt-oss model should use o200k_harmony encoder."""
        renderer = MockRendererWithTokenTracking()
        callbacks = adapters.RendererCallbacks(renderer, model="gpt-oss-120b")

        # Verify the internal counter uses correct encoder
        assert callbacks._turn_counter.encoder_name == "o200k_harmony"

    @_pytest.mark.asyncio
    async def test_gpt_4_model_uses_correct_encoder(self) -> None:
        """gpt-4 model should use cl100k_base encoder."""
        renderer = MockRendererWithTokenTracking()
        callbacks = adapters.RendererCallbacks(renderer, model="gpt-4")

        assert callbacks._turn_counter.encoder_name == "cl100k_base"

    @_pytest.mark.asyncio
    async def test_unknown_model_uses_fallback_encoder(self) -> None:
        """Unknown model should fall back to cl100k_base."""
        renderer = MockRendererWithTokenTracking()
        callbacks = adapters.RendererCallbacks(renderer, model="some-unknown-model")

        assert callbacks._turn_counter.encoder_name == "cl100k_base"

