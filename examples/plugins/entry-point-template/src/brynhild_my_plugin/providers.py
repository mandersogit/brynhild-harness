"""
Example LLM provider for the plugin template.

Providers are registered in pyproject.toml:

    [project.entry-points."brynhild.providers"]
    my-provider = "brynhild_my_plugin.providers:MyProvider"

The entry point value must be the Provider CLASS, not an instance.

Note: This file is included as a template but commented out in pyproject.toml
since most plugins won't need a custom provider.
"""

import typing as _typing

import brynhild.api.base as _base
import brynhild.api.types as _types


class MyProvider(_base.LLMProvider):
    """
    Example LLM provider.

    Demonstrates the required interface for custom providers.
    In practice, you would implement actual API calls here.

    Required properties:
        - name: Provider identifier (e.g., "my-provider")
        - model: Current model being used

    Required methods:
        - complete(): Generate a completion from messages
        - stream(): Stream a completion from messages
    """

    def __init__(
        self,
        model: str = "my-model",
        api_key: str | None = None,
        **kwargs: _typing.Any,
    ) -> None:
        """
        Initialize the provider.

        Args:
            model: Model identifier
            api_key: API key (if needed)
            **kwargs: Additional configuration
        """
        self._model = model
        self._api_key = api_key

    @property
    def name(self) -> str:
        """Provider name - must be implemented."""
        return "my-provider"

    @property
    def model(self) -> str:
        """Current model - must be implemented."""
        return self._model

    async def complete(
        self,
        messages: list[dict[str, _typing.Any]],
        **kwargs: _typing.Any,
    ) -> _types.CompletionResponse:
        """
        Generate a completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            CompletionResponse with the generated content.
        """
        # In a real provider, you would:
        # 1. Format messages for your API
        # 2. Make the API call
        # 3. Parse the response
        # 4. Return a CompletionResponse

        # This is a mock implementation
        return _types.CompletionResponse(
            id="mock-response-id",
            content=f"Mock response from {self.model}",
            stop_reason="stop",
            usage=_types.Usage(input_tokens=10, output_tokens=20),
            tool_uses=[],
        )

    async def stream(
        self,
        messages: list[dict[str, _typing.Any]],
        **kwargs: _typing.Any,
    ) -> _typing.AsyncIterator[_types.StreamEvent]:
        """
        Stream a completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            **kwargs: Additional parameters

        Yields:
            StreamEvent objects as content is generated.
        """
        # In a real provider, you would:
        # 1. Make streaming API call
        # 2. Yield events as they arrive

        # Mock implementation
        yield _types.StreamEvent(
            type="content_block_start",
            index=0,
        )
        yield _types.StreamEvent(
            type="content_block_delta",
            index=0,
            delta={"type": "text_delta", "text": f"Mock stream from {self.model}"},
        )
        yield _types.StreamEvent(
            type="content_block_stop",
            index=0,
        )
        yield _types.StreamEvent(
            type="message_stop",
        )

