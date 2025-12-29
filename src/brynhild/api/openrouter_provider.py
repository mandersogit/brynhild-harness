"""
OpenRouter provider - DEPRECATED LOCATION.

This module re-exports from the new location for backward compatibility.
Import from brynhild.api.providers.openrouter instead.
"""

import brynhild.api.providers.openrouter.provider as _provider

# Re-export from new location
OpenRouterAPIError = _provider.OpenRouterAPIError
OpenRouterProvider = _provider.OpenRouterProvider
OPENROUTER_MODELS = _provider.OPENROUTER_MODELS

__all__ = ["OpenRouterProvider", "OpenRouterAPIError", "OPENROUTER_MODELS"]
