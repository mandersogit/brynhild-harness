"""
Provider factory for creating LLM providers.

Provides a unified interface for creating providers based on configuration.
Supports both builtin providers and plugin-provided providers.

Provider Type Dispatch:
    Providers are created based on the `type` field in their instance config.
    For example, `ollama-behemoth` with `type: ollama` uses the Ollama provider.

⚠️ TEMPORARY ARCHITECTURE: Providers currently accept constructor args directly.
Near-term follow-up will refactor providers to accept ProviderInstanceConfig.
"""

from __future__ import annotations

import contextlib
import logging as _logging
import os as _os
import typing as _typing

import brynhild.api.base as base
import brynhild.constants as _constants

_logger = _logging.getLogger(__name__)

# Cache for loaded plugin providers
_plugin_providers_loaded = False

# Mapping of provider types to their implementations
# Type names are lowercase identifiers (e.g., "ollama", "openrouter")
BUILTIN_PROVIDER_TYPES: dict[str, str] = {
    "ollama": "brynhild.api.providers.ollama.provider",
    "openrouter": "brynhild.api.providers.openrouter.provider",
    # Stubs for future providers - will raise NotImplementedError
    "vllm": "brynhild.api.providers.stubs.vllm",
    "lmstudio": "brynhild.api.providers.stubs.lmstudio",
    "openai": "brynhild.api.providers.stubs.openai",
}


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


def _get_provider_config(
    instance_name: str,
) -> tuple[str, dict[str, _typing.Any]] | None:
    """
    Get provider type and config for an instance name.

    Args:
        instance_name: The provider instance name (e.g., "openrouter", "ollama-behemoth")

    Returns:
        Tuple of (type, config_dict) or None if not found
    """
    try:
        import brynhild.config as config

        settings = config.Settings()
        provider_config = settings.providers.get_provider_config(instance_name)

        if provider_config is None:
            return None

        # Build config dict from model fields AND extras
        config_dict: dict[str, _typing.Any] = {}
        # Add known fields
        if provider_config.base_url is not None:
            config_dict["base_url"] = provider_config.base_url
        if not provider_config.enabled:
            config_dict["enabled"] = False
        config_dict["cache_ttl"] = provider_config.cache_ttl
        # Add any extras
        if provider_config.model_extra:
            config_dict.update(provider_config.model_extra)

        return (provider_config.type, config_dict)
    except Exception as e:
        _logger.debug("Could not load provider config for %s: %s", instance_name, e)
        return None


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
    2. Settings from config files
    3. BRYNHILD_PROVIDERS__DEFAULT environment variable
    4. Auto-detect based on available API keys

    Supports builtin providers (openrouter, ollama) and plugin-provided
    providers discovered from plugin directories.

    The provider name is looked up in `providers.instances` to get the
    `type` field, which determines which provider implementation to use.

    Args:
        provider: Provider instance name ('openrouter', 'ollama-behemoth', etc.)
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

    # Determine provider instance name
    if provider is None:
        # Try config first
        try:
            import brynhild.config as config

            settings = config.Settings()
            provider = settings.providers.default
        except Exception:
            pass

    if provider is None:
        # Legacy env var fallback
        provider = _os.environ.get("BRYNHILD_PROVIDERS__DEFAULT")

    if provider is None:
        # Auto-detect based on available keys
        if _os.environ.get("OPENROUTER_API_KEY"):
            provider = "openrouter"
        else:
            raise ValueError(
                "No provider specified and no API keys found. "
                "Set providers.default in config or OPENROUTER_API_KEY."
            )

    # Get provider type from config
    provider_type: str | None = None
    instance_config: dict[str, _typing.Any] = {}

    config_result = _get_provider_config(provider)
    if config_result is not None:
        provider_type, instance_config = config_result

    # If no config found, assume instance name is the type (for backward compat)
    if provider_type is None:
        # Check if it's a known builtin type
        if provider in BUILTIN_PROVIDER_TYPES:
            provider_type = provider
        else:
            # Check plugins
            try:
                import brynhild.plugins.providers as plugin_providers

                if plugin_providers.get_plugin_provider(provider) is not None:
                    provider_type = provider
            except Exception:
                pass

    if provider_type is None:
        available = get_available_provider_names(load_plugins=load_plugins)
        raise ValueError(
            f"Unknown provider: {provider}. "
            f"Ensure it's declared in providers.instances with a type field. "
            f"Available types: {', '.join(sorted(available))}."
        )

    # Create the appropriate provider
    llm_provider = _create_provider_by_type(
        provider_type=provider_type,
        instance_name=provider,
        instance_config=instance_config,
        model=model,
        api_key=api_key,
    )

    # Auto-attach model profile if requested
    if auto_profile:
        _attach_profile(llm_provider, provider)

    return llm_provider


def _create_provider_by_type(
    provider_type: str,
    instance_name: str,
    instance_config: dict[str, _typing.Any],
    model: str | None,
    api_key: str | None,
) -> base.LLMProvider:
    """
    Create a provider instance by type.

    Args:
        provider_type: The provider type (e.g., "ollama", "openrouter")
        instance_name: The instance name for logging/debugging
        instance_config: Extra config from ProviderInstanceConfig.model_extra
        model: Model to use
        api_key: API key override

    Returns:
        LLMProvider instance

    Raises:
        ValueError: If provider type is unknown
    """
    _logger.debug(
        "Creating provider instance '%s' (type: %s)", instance_name, provider_type
    )

    # ⚠️ TEMPORARY: Pass individual args to providers.
    # Near-term follow-up will refactor providers to accept ProviderInstanceConfig.

    if provider_type == "openrouter":
        import brynhild.api.providers.openrouter.provider as openrouter_provider

        resolved_model = model or _os.environ.get(
            "BRYNHILD_MODELS__DEFAULT",
            _os.environ.get("BRYNHILD_MODEL", _constants.DEFAULT_MODEL),
        )
        return openrouter_provider.OpenRouterProvider(
            api_key=api_key or _os.environ.get("OPENROUTER_API_KEY"),
            model=resolved_model,
        )

    elif provider_type == "ollama":
        import brynhild.api.providers.ollama.provider as ollama_provider

        resolved_model = model or _os.environ.get(
            "BRYNHILD_MODELS__DEFAULT", _os.environ.get("BRYNHILD_MODEL", "llama3")
        )

        # Get base_url from instance config or env var
        base_url = instance_config.get("base_url")
        host = None
        port = None

        if base_url:
            # Parse base_url to extract host/port
            # base_url format: http://hostname:port
            if base_url.startswith("http://"):
                parts = base_url[7:].split(":")
                host = parts[0]
                if len(parts) > 1:
                    with contextlib.suppress(ValueError):
                        port = int(parts[1])
            elif base_url.startswith("https://"):
                parts = base_url[8:].split(":")
                host = parts[0]
                if len(parts) > 1:
                    with contextlib.suppress(ValueError):
                        port = int(parts[1])

        return ollama_provider.OllamaProvider(
            model=resolved_model,
            host=host,
            port=port,
        )

    elif provider_type in ("vllm", "lmstudio", "openai"):
        # Stub providers - will raise NotImplementedError
        module_path = BUILTIN_PROVIDER_TYPES[provider_type]
        import importlib as _importlib

        module = _importlib.import_module(module_path)
        provider_cls_name = {
            "vllm": "VLLMProvider",
            "lmstudio": "LMStudioProvider",
            "openai": "OpenAIProvider",
        }[provider_type]
        provider_cls: type[base.LLMProvider] = getattr(module, provider_cls_name)
        return provider_cls()  # Will raise NotImplementedError

    else:
        # Try plugin providers (pass instance_config for plugin-specific settings)
        plugin_provider = _create_plugin_provider(
            provider_type, model, api_key, instance_config
        )
        if plugin_provider is not None:
            return plugin_provider

        available = get_available_provider_types()
        raise ValueError(
            f"Unknown provider type: {provider_type}. "
            f"Available types: {', '.join(sorted(available))}."
        )


def _create_plugin_provider(
    provider_type: str,
    model: str | None,
    api_key: str | None,
    instance_config: dict[str, _typing.Any] | None = None,
) -> base.LLMProvider | None:
    """
    Try to create a provider from loaded plugins.

    Args:
        provider_type: Provider type name.
        model: Model to use.
        api_key: API key.
        instance_config: Extra config from ProviderInstanceConfig (passed as kwargs).

    Returns:
        LLMProvider instance or None if not found.
    """
    try:
        import brynhild.plugins.providers as plugin_providers

        provider_cls = plugin_providers.get_plugin_provider(provider_type)
        if provider_cls is None:
            return None

        # Resolve model from environment if not provided
        resolved_model = model or _os.environ.get(
            "BRYNHILD_MODELS__DEFAULT", _os.environ.get("BRYNHILD_MODEL")
        )

        # Build kwargs from instance_config
        kwargs: dict[str, _typing.Any] = dict(instance_config) if instance_config else {}
        if resolved_model:
            kwargs["model"] = resolved_model
        if api_key:
            kwargs["api_key"] = api_key

        # Try to instantiate with all kwargs (instance config + model + api_key)
        try:
            return provider_cls(**kwargs)  # type: ignore[no-any-return]
        except TypeError:
            # Fall back to simpler signatures for backwards compatibility
            try:
                if api_key and resolved_model:
                    return provider_cls(model=resolved_model, api_key=api_key)  # type: ignore[no-any-return]
                elif resolved_model:
                    return provider_cls(model=resolved_model)  # type: ignore[no-any-return]
                else:
                    return provider_cls()  # type: ignore[no-any-return]
            except TypeError:
                # Final fallback to no-args construction
                return provider_cls()  # type: ignore[no-any-return]

    except Exception as e:
        _logger.warning("Failed to create plugin provider %s: %s", provider_type, e)
        return None


def _attach_profile(llm_provider: base.LLMProvider, provider_name: str) -> None:
    """
    Attach a model profile to a provider if one is available.

    Profiles are loaded from:
    1. Builtin profiles (from brynhild.profiles.builtin)
    2. Plugin profiles (from plugin profiles/ directories)
    3. User profiles are NOT loaded here (runtime auto-attach uses builtins + plugins)

    Args:
        llm_provider: The provider to attach the profile to
        provider_name: Name of the provider (for resolution context)
    """
    import brynhild.profiles as profiles

    # Load builtin + plugin profiles, but not user profiles
    manager = profiles.ProfileManager(
        load_user_profiles=False,
        load_plugin_profiles=True,
    )
    profile = manager.resolve(llm_provider.model, provider=provider_name)

    # Only attach if we got a non-default profile
    # (default profile has minimal patterns, not worth applying)
    if profile.name != "default":
        llm_provider.profile = profile


def get_available_provider_types() -> set[str]:
    """
    Get set of all available provider type names.

    This includes builtin types and plugin-provided types.

    Returns:
        Set of provider type names
    """
    types = set(BUILTIN_PROVIDER_TYPES.keys())

    _ensure_plugin_providers_loaded()
    try:
        import brynhild.plugins.providers as plugin_providers

        types.update(plugin_providers.get_all_plugin_providers().keys())
    except Exception:
        pass

    return types


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
            "type": "openrouter",
            "description": "OpenRouter (access to multiple model providers)",
            "key_env_var": "OPENROUTER_API_KEY",
            "key_configured": bool(_os.environ.get("OPENROUTER_API_KEY")),
            "default_model": _constants.DEFAULT_MODEL,
            "available": True,
            "source": "builtin",
        },
        {
            "name": "ollama",
            "type": "ollama",
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
            "type": "vllm",
            "description": "vLLM (self-hosted inference server)",
            "key_env_var": "VLLM_API_KEY",
            "key_configured": bool(_os.environ.get("VLLM_API_KEY")),
            "default_model": None,  # Model specified by server
            "available": False,  # Not yet implemented
            "source": "builtin",
        },
        {
            "name": "lmstudio",
            "type": "lmstudio",
            "description": "LM Studio (local inference, enterprise approved)",
            "key_env_var": None,
            "key_configured": True,
            "default_model": None,
            "available": False,  # Not yet implemented
            "source": "builtin",
        },
        {
            "name": "openai",
            "type": "openai",
            "description": "OpenAI direct API (requires OPENAI_API_KEY)",
            "key_env_var": "OPENAI_API_KEY",
            "key_configured": bool(_os.environ.get("OPENAI_API_KEY")),
            "default_model": "gpt-4",
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
                    "type": name,  # Plugin type = name
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

    This includes configured instance names from settings plus default types.

    Args:
        load_plugins: Whether to include plugin providers (default True)

    Returns:
        Set of provider names
    """
    names = {"openrouter", "ollama"}  # Always available builtins

    # Add configured instances from settings
    try:
        import brynhild.config as config

        settings = config.Settings()
        names.update(settings.providers.instances.keys())
    except Exception:
        pass

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
    # Check config first
    try:
        import brynhild.config as config

        settings = config.Settings()
        return settings.providers.default
    except Exception:
        pass

    # Check explicit environment configuration
    if provider := _os.environ.get("BRYNHILD_PROVIDERS__DEFAULT"):
        return provider

    # Legacy env var
    if provider := _os.environ.get("BRYNHILD_PROVIDER"):
        return provider

    # Default to openrouter if key is available
    if _os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"

    return None
