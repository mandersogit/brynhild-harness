"""
Ollama provider - DEPRECATED LOCATION.

This module re-exports from the new location for backward compatibility.
Import from brynhild.api.providers.ollama instead.
"""

import brynhild.api.providers.ollama.provider as _provider

# Re-export from new location
OllamaProvider = _provider.OllamaProvider

__all__ = ["OllamaProvider"]
