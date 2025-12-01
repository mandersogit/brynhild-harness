"""
Custom LLM provider loading from plugin directories.

Providers are Python modules in a plugin's providers/ directory that define
a Provider class implementing the LLMProvider interface.
"""

from __future__ import annotations

import importlib.util as _importlib_util
import logging as _logging
import pathlib as _pathlib
import sys as _sys
import typing as _typing

_logger = _logging.getLogger(__name__)

# Type alias for provider classes
ProviderClass = type[_typing.Any]


class ProviderLoadError(Exception):
    """Raised when a provider fails to load."""

    pass


def load_provider_module(
    provider_path: _pathlib.Path,
    plugin_name: str = "",
) -> _typing.Any:
    """
    Dynamically load a Python module from a file path.

    Args:
        provider_path: Path to the .py file.
        plugin_name: Plugin name (for module naming).

    Returns:
        The loaded module.

    Raises:
        ProviderLoadError: If module fails to load.
    """
    if not provider_path.exists():
        raise ProviderLoadError(f"Provider file not found: {provider_path}")

    if not provider_path.suffix == ".py":
        raise ProviderLoadError(f"Provider file must be .py: {provider_path}")

    # Generate a unique module name
    provider_name = provider_path.stem
    module_name = f"brynhild_plugins.{plugin_name}.providers.{provider_name}"

    try:
        spec = _importlib_util.spec_from_file_location(module_name, provider_path)
        if spec is None or spec.loader is None:
            raise ProviderLoadError(f"Cannot load module spec for: {provider_path}")

        module = _importlib_util.module_from_spec(spec)
        _sys.modules[module_name] = module
        spec.loader.exec_module(module)

        return module
    except Exception as e:
        raise ProviderLoadError(f"Failed to load provider {provider_path}: {e}") from e


def get_provider_class_from_module(
    module: _typing.Any,
    expected_name: str | None = None,  # noqa: ARG001 - reserved for future use
) -> ProviderClass | None:
    """
    Find a Provider class in a loaded module.

    Looks for a class that:
    1. Is named 'Provider' or matches expected_name
    2. Has a 'name' property (duck typing check for LLMProvider)

    Args:
        module: The loaded module.
        expected_name: Optional expected provider name.

    Returns:
        The Provider class, or None if not found.
    """
    # First try to find a class named 'Provider'
    if hasattr(module, "Provider"):
        provider_cls = module.Provider
        if _is_provider_class(provider_cls):
            return provider_cls  # type: ignore[no-any-return]

    # Look for any class with required LLMProvider attributes
    for attr_name in dir(module):
        if attr_name.startswith("_"):
            continue
        attr = getattr(module, attr_name)
        if _is_provider_class(attr):
            return attr  # type: ignore[no-any-return]

    return None


def _is_provider_class(obj: _typing.Any) -> bool:
    """Check if an object looks like an LLMProvider class."""
    if not isinstance(obj, type):
        return False

    # Duck typing: must have 'name' property and 'complete' method
    # (basic LLMProvider interface)
    return (
        hasattr(obj, "name")
        and hasattr(obj, "model")
        and (
            callable(getattr(obj, "complete", None))
            or callable(getattr(obj, "stream", None))
        )
    )


class ProviderLoader:
    """
    Loads custom LLM providers from plugin directories.

    Providers are Python modules in a plugin's providers/ directory that define
    a class implementing the LLMProvider interface.
    """

    def __init__(self) -> None:
        """Initialize the provider loader."""
        self._loaded_providers: dict[str, ProviderClass] = {}

    def load_from_file(
        self,
        provider_path: _pathlib.Path,
        plugin_name: str = "",
    ) -> ProviderClass | None:
        """
        Load a single provider from a Python file.

        Args:
            provider_path: Path to the .py file.
            plugin_name: Plugin name.

        Returns:
            The Provider class, or None if not found/invalid.
        """
        try:
            module = load_provider_module(provider_path, plugin_name)
            provider_cls = get_provider_class_from_module(module, provider_path.stem)
            if provider_cls is not None:
                # Get the provider name from the class
                # Try to instantiate briefly to get name, or use module name
                provider_name = provider_path.stem
                try:
                    # Check if class has a NAME class attribute
                    if hasattr(provider_cls, "PROVIDER_NAME"):
                        provider_name = provider_cls.PROVIDER_NAME
                except Exception:
                    pass
                self._loaded_providers[provider_name] = provider_cls
            return provider_cls
        except ProviderLoadError as e:
            _logger.warning("Failed to load provider: %s", e)
            return None

    def load_from_directory(
        self,
        providers_dir: _pathlib.Path,
        plugin_name: str = "",
    ) -> dict[str, ProviderClass]:
        """
        Load all providers from a directory.

        Args:
            providers_dir: Path to providers/ directory.
            plugin_name: Plugin name.

        Returns:
            Dict mapping provider name to Provider class.
        """
        providers: dict[str, ProviderClass] = {}

        if not providers_dir.is_dir():
            return providers

        for py_file in sorted(providers_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue  # Skip __init__.py and private modules

            provider_cls = self.load_from_file(py_file, plugin_name)
            if provider_cls is not None:
                # Use PROVIDER_NAME if defined, else filename
                if hasattr(provider_cls, "PROVIDER_NAME"):
                    provider_name = provider_cls.PROVIDER_NAME
                else:
                    provider_name = py_file.stem
                providers[provider_name] = provider_cls

        return providers

    def load_from_plugin(
        self,
        plugin_path: _pathlib.Path,
        plugin_name: str,
    ) -> dict[str, ProviderClass]:
        """
        Load providers from a plugin directory.

        Args:
            plugin_path: Root path of the plugin.
            plugin_name: Plugin name.

        Returns:
            Dict mapping provider name to Provider class.
        """
        providers_dir = plugin_path / "providers"
        return self.load_from_directory(providers_dir, plugin_name)

    def get_loaded_providers(self) -> dict[str, ProviderClass]:
        """Get all providers loaded so far."""
        return dict(self._loaded_providers)


# Global registry of plugin providers
_plugin_providers: dict[str, ProviderClass] = {}


def register_plugin_provider(name: str, provider_cls: ProviderClass) -> None:
    """
    Register a plugin provider globally.

    Args:
        name: Provider name (used in BRYNHILD_PROVIDER).
        provider_cls: Provider class implementing LLMProvider.
    """
    _plugin_providers[name] = provider_cls
    _logger.info("Registered plugin provider: %s", name)


def get_plugin_provider(name: str) -> ProviderClass | None:
    """
    Get a plugin provider by name.

    Args:
        name: Provider name.

    Returns:
        Provider class or None if not found.
    """
    return _plugin_providers.get(name)


def get_all_plugin_providers() -> dict[str, ProviderClass]:
    """Get all registered plugin providers."""
    return dict(_plugin_providers)


def load_all_plugin_providers() -> dict[str, ProviderClass]:
    """
    Discover and load all plugin providers.

    Searches plugin paths and loads providers from any plugin
    that declares them in its manifest.

    Returns:
        Dict mapping provider name to Provider class.
    """
    import brynhild.plugins.discovery as discovery
    import brynhild.plugins.loader as loader

    plugin_loader = loader.PluginLoader()
    provider_loader = ProviderLoader()

    # Get all plugin search paths
    paths = discovery.get_plugin_search_paths()

    for search_path in paths:
        if not search_path.exists():
            continue

        # Discover plugins in this path
        for plugin_dir in search_path.iterdir():
            if not plugin_dir.is_dir():
                continue

            manifest_path = plugin_dir / "plugin.yaml"
            if not manifest_path.exists():
                continue

            try:
                plugin = plugin_loader.load(plugin_dir)
                if plugin and plugin.has_providers():
                    providers = provider_loader.load_from_plugin(
                        plugin.path,
                        plugin.name,
                    )
                    for name, cls in providers.items():
                        register_plugin_provider(name, cls)
            except Exception as e:
                _logger.warning("Failed to load plugin providers from %s: %s", plugin_dir, e)

    return get_all_plugin_providers()

