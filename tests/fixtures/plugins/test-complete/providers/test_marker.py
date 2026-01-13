"""
Test provider that wraps responses with markers.

This provider doesn't connect to any real LLM - it just returns
canned responses with markers to prove the plugin system works.
"""

from __future__ import annotations

import typing as _typing


class Provider:
    """Mock provider for testing plugin provider loading."""

    _is_brynhild_duck_typed = True  # Explicit duck-typing declaration
    PROVIDER_NAME = "test-marker"

    def __init__(
        self,
        model: str = "test-model",
        **kwargs: _typing.Any,  # noqa: ARG002 - API compatibility
    ) -> None:
        """Initialize the test provider."""
        self._model = model
        self._call_count = 0

    @property
    def name(self) -> str:
        return "test-marker"

    @property
    def model(self) -> str:
        return self._model

    def supports_tools(self) -> bool:
        return True

    def supports_reasoning(self) -> bool:
        return False

    async def complete(
        self,
        messages: list[dict[str, _typing.Any]],
        **kwargs: _typing.Any,  # noqa: ARG002 - API compatibility
    ) -> _typing.Any:
        """Return a canned response with marker."""
        self._call_count += 1

        # Import types to create proper response
        import brynhild.api.types as types

        # Get last user message
        last_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_message = str(msg.get("content", ""))
                break

        content = (
            f"[TEST-MARKER-PROVIDER] Call #{self._call_count}\n"
            f"Model: {self._model}\n"
            f"Last message: {last_message[:100]}"
        )

        return types.CompletionResponse(
            id=f"test-{self._call_count}",
            content=content,
            stop_reason="end_turn",
            usage=types.Usage(input_tokens=10, output_tokens=20),
            tool_uses=[],
        )

    async def stream(
        self,
        messages: list[dict[str, _typing.Any]],  # noqa: ARG002 - API compatibility
        **kwargs: _typing.Any,  # noqa: ARG002 - API compatibility
    ) -> _typing.AsyncIterator[_typing.Any]:
        """Stream a canned response with markers."""
        import brynhild.api.types as types

        self._call_count += 1

        yield types.StreamEvent(type="message_start")
        yield types.StreamEvent(
            type="text_delta",
            text=f"[TEST-MARKER-PROVIDER-STREAM] Call #{self._call_count}",
        )
        yield types.StreamEvent(type="message_stop")

    async def close(self) -> None:
        """No-op close."""
        pass
