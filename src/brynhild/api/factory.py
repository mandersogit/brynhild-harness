"""
Provider factory for creating LLM providers.

Provides a unified interface for creating providers based on configuration.
Supports both builtin providers and plugin-provided providers.
"""

from __future__ import annotations

import logging as _logging
import os as _os
import typing as _typing

import brynhild.api.base as base
import brynhild.constants as _constants

_logger = _logging.getLogger(__name__)

# Cache for loaded plugin providers
_plugin_providers_loaded = False


def _ensure_plugin_providers_loaded() -> None:
    """Load plugin providers if not already loaded."""
    global _plugin_providers_loaded
    if _plugin_providers_loaded:
        return

    try:
        import brynhild.plugins.providers as plugin_providers

        plugin_providers.load_all_plugin_providers()
        _plugin_providers_loaded = True
    except Exception as e:
        _logger.warning("Failed to load plugin providers: %s", e)
        _plugin_providers_loaded = True  # Don't retry on failure


def create_provider(
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    *,
    auto_profile: bool = True,
    load_plugins: bool = True,
) -> base.LLMProvider:
    """
    Create an LLM provider based on configuration.

    Provider selection (in order of precedence):
    1. Explicit `provider` parameter
    2. BRYNHILD_PROVIDER environment variable
    3. Auto-detect based on available API keys

    Supports builtin providers (openrouter, ollama) and plugin-provided
    providers discovered from plugin directories.

    Args:
        provider: Provider name ('openrouter', 'ollama', or plugin provider name)
        model: Model to use (provider-specific format)
        api_key: API key (defaults to environment variable for provider)
        auto_profile: Automatically attach model profile if available (default True)
        load_plugins: Whether to load plugin providers (default True)

    Returns:
        Configured LLMProvider instance with model profile attached (if available)

    Raises:
        ValueError: If no provider can be determined or API key is missing
    """
    # Load plugin providers first
    if load_plugins:
        _ensure_plugin_providers_loaded()

    # Determine provider
    if provider is None:
        provider = _os.environ.get("BRYNHILD_PROVIDER")

    if provider is None:
        # Auto-detect based on available keys
        if _os.environ.get("OPENROUTER_API_KEY"):
            provider = "openrouter"
        # TODO: Add detection for ollama (check if server running?)
        # TODO: Add detection for vllm endpoint
        else:
            raise ValueError(
                "No provider specified and no API keys found. "
                "Set BRYNHILD_PROVIDER or OPENROUTER_API_KEY."
            )

    # Create the appropriate provider
    llm_provider: base.LLMProvider

    if provider == "openrouter":
        import brynhild.api.openrouter_provider as openrouter_provider

        resolved_model = model or _os.environ.get(
            "BRYNHILD_MODEL", _constants.DEFAULT_MODEL
        )
        llm_provider = openrouter_provider.OpenRouterProvider(
            api_key=api_key or _os.environ.get("OPENROUTER_API_KEY"),
            model=resolved_model,
        )

    elif provider == "ollama":
        import brynhild.api.ollama_provider as ollama_provider

        resolved_model = model or _os.environ.get("BRYNHILD_MODEL", "llama3")
        llm_provider = ollama_provider.OllamaProvider(
            model=resolved_model,
            # Host/port handled via OLLAMA_HOST env var
        )

    elif provider == "vllm":
        raise NotImplementedError(
            "vLLM provider not yet implemented. See TODO in backlog."
        )

    elif provider == "vertex":
        raise NotImplementedError(
            "Vertex AI provider not yet implemented. See TODO in backlog."
        )

    else:
        # Try plugin providers
        plugin_provider = _create_plugin_provider(provider, model, api_key)
        if plugin_provider is None:
            available = get_available_provider_names()
            raise ValueError(
                f"Unknown provider: {provider}. "
                f"Available: {', '.join(sorted(available))}."
            )
        llm_provider = plugin_provider

    # Auto-attach model profile if requested
    if auto_profile:
        _attach_profile(llm_provider, provider)

    return llm_provider


def _create_plugin_provider(
    provider: str,
    model: str | None,
    api_key: str | None,
) -> base.LLMProvider | None:
    """
    Try to create a provider from loaded plugins.

    Args:
        provider: Provider name.
        model: Model to use.
        api_key: API key.

    Returns:
        LLMProvider instance or None if not found.
    """
    try:
        import brynhild.plugins.providers as plugin_providers

        provider_cls = plugin_providers.get_plugin_provider(provider)
        if provider_cls is None:
            return None

        # Resolve model from environment if not provided
        resolved_model = model or _os.environ.get("BRYNHILD_MODEL")

        # Try to instantiate with common argument patterns
        # Plugin providers should accept at least model and optional api_key
        try:
            if api_key:
                return provider_cls(model=resolved_model, api_key=api_key)  # type: ignore[no-any-return]
            elif resolved_model:
                return provider_cls(model=resolved_model)  # type: ignore[no-any-return]
            else:
                return provider_cls()  # type: ignore[no-any-return]
        except TypeError:
            # Fall back to no-args construction
            return provider_cls()  # type: ignore[no-any-return]

    except Exception as e:
        _logger.warning("Failed to create plugin provider %s: %s", provider, e)
        return None


def _attach_profile(llm_provider: base.LLMProvider, provider_name: str) -> None:
    """
    Attach a model profile to a provider if one is available.

    Args:
        llm_provider: The provider to attach the profile to
        provider_name: Name of the provider (for resolution context)
    """
    import brynhild.profiles as profiles

    manager = profiles.ProfileManager(load_user_profiles=False)
    profile = manager.resolve(llm_provider.model, provider=provider_name)

    # Only attach if we got a non-default profile
    # (default profile has minimal patterns, not worth applying)
    if profile.name != "default":
        llm_provider.profile = profile


def get_available_providers(load_plugins: bool = True) -> list[dict[str, _typing.Any]]:
    """
    Get list of available providers and their configuration status.

    Args:
        load_plugins: Whether to include plugin providers (default True)

    Returns:
        List of provider info dicts with name, available, and key_configured fields
    """
    providers: list[dict[str, _typing.Any]] = [
        {
            "name": "openrouter",
            "description": "OpenRouter (access to multiple model providers)",
            "key_env_var": "OPENROUTER_API_KEY",
            "key_configured": bool(_os.environ.get("OPENROUTER_API_KEY")),
            "default_model": _constants.DEFAULT_MODEL,
            "available": True,
            "source": "builtin",
        },
        {
            "name": "ollama",
            "description": "Ollama (local or remote models via OLLAMA_HOST)",
            "key_env_var": None,  # No API key needed
            "key_configured": True,  # Assumes server is reachable
            "default_model": "llama3",
            "host_env_var": "BRYNHILD_OLLAMA_HOST or OLLAMA_HOST",
            "available": True,
            "source": "builtin",
        },
        {
            "name": "vllm",
            "description": "vLLM (self-hosted inference server)",
            "key_env_var": "VLLM_API_KEY",
            "key_configured": bool(_os.environ.get("VLLM_API_KEY")),
            "default_model": None,  # Model specified by server
            "available": False,  # Not yet implemented
            "source": "builtin",
        },
        {
            "name": "vertex",
            "description": "Google Vertex AI (enterprise)",
            "key_env_var": "GOOGLE_APPLICATION_CREDENTIALS",
            "key_configured": bool(_os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")),
            "default_model": "gemini-pro",
            "available": False,  # Not yet implemented
            "source": "builtin",
        },
    ]

    # Add plugin providers
    if load_plugins:
        _ensure_plugin_providers_loaded()
        try:
            import brynhild.plugins.providers as plugin_providers

            for name, cls in plugin_providers.get_all_plugin_providers().items():
                # Get description from class docstring or attribute
                description = getattr(cls, "__doc__", None) or f"Plugin provider: {name}"
                if description:
                    description = description.strip().split("\n")[0]  # First line only

                providers.append({
                    "name": name,
                    "description": description,
                    "key_env_var": None,
                    "key_configured": True,  # Assume plugin handles auth
                    "default_model": None,
                    "available": True,
                    "source": "plugin",
                })
        except Exception as e:
            _logger.warning("Failed to get plugin providers: %s", e)

    return providers


def get_available_provider_names(load_plugins: bool = True) -> set[str]:
    """
    Get set of all available provider names.

    Args:
        load_plugins: Whether to include plugin providers (default True)

    Returns:
        Set of provider names
    """
    names = {"openrouter", "ollama"}  # Always available builtins

    if load_plugins:
        _ensure_plugin_providers_loaded()
        try:
            import brynhild.plugins.providers as plugin_providers

            names.update(plugin_providers.get_all_plugin_providers().keys())
        except Exception:
            pass

    return names


def get_default_provider() -> str | None:
    """
    Determine the default provider based on configuration.

    Returns:
        Provider name or None if no provider can be determined
    """
    # Check explicit configuration first
    if provider := _os.environ.get("BRYNHILD_PROVIDER"):
        return provider

    # Default to openrouter if key is available
    if _os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"

    return None
