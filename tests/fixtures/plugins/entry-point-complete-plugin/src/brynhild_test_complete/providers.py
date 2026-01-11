"""
Test provider for entry point discovery integration tests.

Demonstrates provider registration via 'brynhild.providers' entry point.
"""

from __future__ import annotations

import typing as _typing

import brynhild.api.base as _base
import brynhild.api.types as _types


class MockProvider(_base.LLMProvider):
    """
    A mock LLM provider for testing entry point provider discovery.

    Returns canned responses without making API calls.
    """

    # Class attribute used for provider identification
    PROVIDER_NAME = "test-mock"

    def __init__(
        self,
        *,
        model: str = "test-model",
        api_key: str | None = None,
        **kwargs: _typing.Any,
    ) -> None:
        """Initialize the mock provider."""
        self._model = model
        self._api_key = api_key
        self._call_count = 0
        # Store any extra kwargs for testing
        self._extra_kwargs = kwargs

    @property
    def name(self) -> str:
        return "test-mock"

    @property
    def model(self) -> str:
        return self._model

    @property
    def supports_tools(self) -> bool:
        return True

    @property
    def supports_streaming(self) -> bool:
        return True

    async def complete(
        self,
        messages: list[_types.Message],
        *,
        tools: list[_types.Tool] | None = None,
        **kwargs: _typing.Any,
    ) -> _types.CompletionResponse:
        """Return a canned completion response."""
        self._call_count += 1

        # Create a simple response
        return _types.CompletionResponse(
            id=f"mock-{self._call_count}",
            content=f"Mock response #{self._call_count} for model {self.model}",
            tool_uses=[],
            stop_reason="stop",
            usage=_types.Usage(
                input_tokens=100,
                output_tokens=50,
            ),
        )

    async def stream(
        self,
        messages: list[_types.Message],
        *,
        tools: list[_types.Tool] | None = None,
        **kwargs: _typing.Any,
    ) -> _typing.AsyncIterator[_types.StreamEvent]:
        """Return mock stream events."""
        self._call_count += 1

        # Yield a text chunk
        yield _types.StreamEvent(
            type="text_delta",
            text=f"Mock streaming response #{self._call_count}",
        )

        # Yield the stop event
        yield _types.StreamEvent(
            type="message_stop",
            stop_reason="stop",
            usage=_types.Usage(
                input_tokens=100,
                output_tokens=50,
            ),
        )

    def get_call_count(self) -> int:
        """Get the number of calls made to this provider (for testing)."""
        return self._call_count

    def get_extra_kwargs(self) -> dict[str, _typing.Any]:
        """Get extra kwargs passed to constructor (for testing)."""
        return self._extra_kwargs

