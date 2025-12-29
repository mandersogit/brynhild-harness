"""
Provider implementations for LLM APIs.

Each provider is in its own submodule for clean separation.
Built-in providers: ollama, openrouter
Future providers: openai, lmstudio, vllm (stubs)
"""

import brynhild.api.providers.ollama.provider as _ollama
import brynhild.api.providers.openrouter.provider as _openrouter

# Re-export providers for convenient access
OllamaProvider = _ollama.OllamaProvider
OpenRouterAPIError = _openrouter.OpenRouterAPIError
OpenRouterProvider = _openrouter.OpenRouterProvider

__all__ = [
    "OllamaProvider",
    "OpenRouterProvider",
    "OpenRouterAPIError",
]
