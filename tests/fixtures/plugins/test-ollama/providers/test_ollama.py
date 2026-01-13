"""
Test Ollama provider - wraps the builtin Ollama provider with verification markers.

This provider is used to verify that the plugin provider system works correctly.
It adds distinctive markers to prove the plugin implementation is being used.
"""

from __future__ import annotations

import sys as _sys
import typing as _typing

# Print immediately when module is loaded - this proves the plugin was found
print("[TEST-PLUGIN] test_ollama.py module loaded!", file=_sys.stderr)


class Provider:
    """Test Ollama provider with verification markers.

    Wraps the builtin Ollama provider but adds markers to prove
    the plugin version is being used, not the builtin.
    """

    _is_brynhild_duck_typed = True  # Explicit duck-typing declaration
    PROVIDER_NAME = "test-ollama"

    # Class-level flag to track instantiation
    _instance_count = 0

    def __init__(
        self,
        model: str = "llama3",
        host: str | None = None,
    ) -> None:
        """Initialize the test provider."""
        Provider._instance_count += 1
        print(
            f"[TEST-PLUGIN] Provider.__init__ called! "
            f"Instance #{Provider._instance_count}, model={model}",
            file=_sys.stderr,
        )

        # Import and wrap the real Ollama provider
        import brynhild.api.ollama_provider as ollama_provider

        self._wrapped = ollama_provider.OllamaProvider(
            model=model,
            host=host,
        )
        self._model = model

    @property
    def name(self) -> str:
        """Provider name - distinctive to prove plugin is used."""
        return "test-ollama"

    @property
    def model(self) -> str:
        """Current model being used."""
        return self._model

    def supports_tools(self) -> bool:
        """Delegate to wrapped provider."""
        return self._wrapped.supports_tools()

    def supports_reasoning(self) -> bool:
        """Delegate to wrapped provider."""
        return self._wrapped.supports_reasoning()

    async def complete(
        self,
        messages: list[dict[str, _typing.Any]],
        *,
        system: str | None = None,
        tools: list[_typing.Any] | None = None,
        max_tokens: int = 8192,
        use_profile: bool = True,
    ) -> _typing.Any:
        """Complete with verification marker.

        Adds a prefix to prove the plugin provider was used.
        """
        print("[TEST-PLUGIN] complete() called!", file=_sys.stderr)

        response = await self._wrapped.complete(
            messages,
            system=system,
            tools=tools,
            max_tokens=max_tokens,
            use_profile=use_profile,
        )

        # Add marker to response content to prove plugin was used
        if hasattr(response, "content") and response.content:
            # Modify the response to add our marker
            response.content = f"[TEST-PLUGIN-RESPONSE] {response.content}"

        return response

    async def stream(
        self,
        messages: list[dict[str, _typing.Any]],
        *,
        system: str | None = None,
        tools: list[_typing.Any] | None = None,
        max_tokens: int = 8192,
        use_profile: bool = True,
    ) -> _typing.AsyncIterator[_typing.Any]:
        """Stream with verification marker.

        Yields a marker event first to prove plugin provider was used.
        """
        print("[TEST-PLUGIN] stream() called!", file=_sys.stderr)

        # Import the types we need
        import brynhild.api.types as types

        # Yield a marker event first
        yield types.StreamEvent(
            type="text_delta",
            text="[TEST-PLUGIN-STREAM] ",
        )

        # Then delegate to wrapped provider
        async for event in self._wrapped.stream(
            messages,
            system=system,
            tools=tools,
            max_tokens=max_tokens,
            use_profile=use_profile,
        ):
            yield event

    async def close(self) -> None:
        """Close the wrapped provider."""
        print("[TEST-PLUGIN] close() called!", file=_sys.stderr)
        await self._wrapped.close()


# Print when module finishes loading
print("[TEST-PLUGIN] test_ollama.py module fully loaded!", file=_sys.stderr)
