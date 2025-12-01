"""
LLM API providers for Brynhild.

Provides a unified interface for different LLM providers:
- OpenRouter (multiple models via single API) - supported
- Ollama (local or remote models) - supported
- vLLM (self-hosted inference) - planned
- Vertex AI (Google Cloud) - planned for enterprise use

Note: We use provider aggregators and self-hosted solutions rather than
direct APIs from single-model-family labs (e.g., no direct Anthropic/OpenAI SDKs).
"""

from brynhild.api.base import LLMProvider
from brynhild.api.factory import (
    create_provider,
    get_available_providers,
    get_default_provider,
)
from brynhild.api.types import (
    CompletionResponse,
    ContentBlock,
    Message,
    StreamEvent,
    Tool,
    ToolResult,
    ToolUse,
    Usage,
)

__all__ = [
    # Base class
    "LLMProvider",
    # Factory
    "create_provider",
    "get_available_providers",
    "get_default_provider",
    # Exceptions
    "OpenRouterAPIError",
    # Types
    "CompletionResponse",
    "ContentBlock",
    "Message",
    "StreamEvent",
    "Tool",
    "ToolResult",
    "ToolUse",
    "Usage",
]


import typing as _typing


# Lazy imports for providers (avoid loading heavy dependencies unless needed)
def __getattr__(name: str) -> _typing.Any:
    if name == "OpenRouterProvider":
        from brynhild.api.openrouter_provider import OpenRouterProvider

        return OpenRouterProvider
    if name == "OllamaProvider":
        from brynhild.api.ollama_provider import OllamaProvider

        return OllamaProvider
    if name == "OpenRouterAPIError":
        from brynhild.api.openrouter_provider import OpenRouterAPIError

        return OpenRouterAPIError
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
