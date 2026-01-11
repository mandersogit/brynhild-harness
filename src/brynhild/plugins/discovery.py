"""
Plugin discovery from standard locations and entry points.

Plugins are discovered from (in priority order, lowest to highest):
1. ~/.config/brynhild/plugins/ - User plugins (directory)
2. $BRYNHILD_PLUGIN_PATH - Custom paths (directory, colon-separated)
3. Project .brynhild/plugins/ - Project-local plugins (directory)
4. Entry points (brynhild.plugins) - Pip-installed plugins (highest priority)

Entry point plugins override directory plugins with the same name.
"""

from __future__ import annotations

import importlib.metadata as _meta
import logging as _logging
import os as _os
import pathlib as _pathlib
import typing as _typing

import brynhild.plugins.loader as loader
import brynhild.plugins.manifest as manifest

_logger = _logging.getLogger(__name__)


def get_global_plugins_path() -> _pathlib.Path:
    """Get the path to global plugins directory."""
    return _pathlib.Path.home() / ".config" / "brynhild" / "plugins"


def get_project_plugins_path(project_root: _pathlib.Path) -> _pathlib.Path:
    """Get the path to project-local plugins directory."""
    return project_root / ".brynhild" / "plugins"


def get_plugin_search_paths(
    project_root: _pathlib.Path | None = None,
) -> list[_pathlib.Path]:
    """
    Get all plugin search paths in priority order.

    Args:
        project_root: Project root directory. If None, only global
                      and env paths are included.

    Returns:
        List of paths to search (lowest to highest priority).
    """
    paths: list[_pathlib.Path] = []

    # 1. Global plugins (lowest priority)
    paths.append(get_global_plugins_path())

    # 2. Environment variable paths
    env_path = _os.environ.get("BRYNHILD_PLUGIN_PATH", "")
    if env_path:
        for p in env_path.split(":"):
            p = p.strip()
            if p:
                paths.append(_pathlib.Path(p).expanduser().resolve())

    # 3. Project-local plugins (highest priority)
    if project_root is not None:
        paths.append(get_project_plugins_path(project_root))

    return paths


def _entry_points_disabled() -> bool:
    """Check if entry point plugin discovery is disabled.

    Controlled by BRYNHILD_DISABLE_ENTRY_POINT_PLUGINS environment variable.
    Useful for testing and debugging.
    """
    return _os.environ.get("BRYNHILD_DISABLE_ENTRY_POINT_PLUGINS", "").lower() in (
        "1", "true", "yes"
    )


def discover_from_entry_points() -> dict[str, manifest.Plugin]:
    """
    Discover plugins registered via setuptools entry points.

    Scans the 'brynhild.plugins' entry point group for pip-installed
    plugins. Each entry point should reference a callable that returns
    either a Plugin or PluginManifest instance.

    Entry point format in pyproject.toml:
        [project.entry-points."brynhild.plugins"]
        my-plugin = "my_package:register"

    The register function should return:
        - A Plugin instance (fully configured)
        - A PluginManifest instance (wrapped automatically)

    Can be disabled by setting BRYNHILD_DISABLE_ENTRY_POINT_PLUGINS=1.

    Returns:
        Dict mapping plugin name to Plugin instance.
    """
    if _entry_points_disabled():
        _logger.debug("Entry point plugin discovery disabled by environment variable")
        return {}

    plugins: dict[str, manifest.Plugin] = {}

    # Python 3.10+ supports the group= keyword argument
    eps = _meta.entry_points(group="brynhild.plugins")

    for ep in eps:
        try:
            # Load the register function from the entry point
            register_fn = ep.load()

            # Call it to get the Plugin or PluginManifest
            plugin = _load_plugin_from_entry_point(ep, register_fn)

            if plugin is not None:
                plugins[plugin.name] = plugin
                _logger.debug(
                    "Discovered plugin '%s' v%s from package '%s'",
                    plugin.name,
                    plugin.version,
                    getattr(ep.dist, "name", "unknown") if ep.dist else "unknown",
                )
        except Exception as e:
            _logger.warning(
                "Failed to load plugin from entry point '%s': %s",
                ep.name,
                e,
            )

    return plugins


def _load_plugin_from_entry_point(
    ep: _meta.EntryPoint,
    register_fn: _typing.Callable[[], manifest.Plugin | manifest.PluginManifest],
) -> manifest.Plugin | None:
    """
    Load a Plugin from an entry point's register function.

    Supports two registration patterns:
    1. register() returns a Plugin directly
    2. register() returns a PluginManifest (we wrap it in a Plugin)

    Args:
        ep: The entry point being loaded.
        register_fn: The callable loaded from the entry point.

    Returns:
        Plugin instance with entry point metadata attached, or None if invalid.
    """
    result = register_fn()

    if isinstance(result, manifest.Plugin):
        plugin = result
    elif isinstance(result, manifest.PluginManifest):
        # Wrap manifest in Plugin with synthetic path
        plugin = manifest.Plugin(
            manifest=result,
            path=_pathlib.Path("<entry-point>"),
        )
    else:
        _logger.warning(
            "Entry point '%s' returned unexpected type: %s (expected Plugin or PluginManifest)",
            ep.name,
            type(result).__name__,
        )
        return None

    # Attach entry point metadata
    plugin.source = "entry_point"
    if ep.dist:
        plugin.package_name = ep.dist.name
        plugin.package_version = ep.dist.version

    return plugin


class PluginDiscovery:
    """
    Discovers plugins from standard locations.

    Scans plugin directories and returns discovered Plugin instances.
    Later sources (project-local) have higher priority than earlier
    sources (global) - plugins with the same name from later sources
    replace earlier ones.
    """

    def __init__(
        self,
        project_root: _pathlib.Path | None = None,
        search_paths: list[_pathlib.Path] | None = None,
    ) -> None:
        """
        Initialize plugin discovery.

        Args:
            project_root: Project root for local plugin discovery.
            search_paths: Custom search paths (overrides default locations).
        """
        self._project_root = project_root
        self._search_paths = search_paths
        self._loader = loader.PluginLoader()

    def get_search_paths(self) -> list[_pathlib.Path]:
        """Get the search paths in use."""
        if self._search_paths is not None:
            return self._search_paths
        return get_plugin_search_paths(self._project_root)

    def discover(self) -> dict[str, manifest.Plugin]:
        """
        Discover all plugins from entry points and directory search paths.

        Priority order (highest wins):
        1. Entry points (brynhild.plugins) - pip-installed packages
        2. Project directory (.brynhild/plugins/)
        3. Environment variable ($BRYNHILD_PLUGIN_PATH)
        4. Global directory (~/.config/brynhild/plugins/)

        Returns:
            Dict mapping plugin name to Plugin instance.
        """
        plugins: dict[str, manifest.Plugin] = {}

        # 1. Directory-based plugins (lowest priority first)
        for search_path in self.get_search_paths():
            if not search_path.is_dir():
                continue

            for plugin_dir in sorted(search_path.iterdir()):
                if not plugin_dir.is_dir():
                    continue

                manifest_path = plugin_dir / "plugin.yaml"
                if not manifest_path.exists():
                    continue

                try:
                    plugin = self._loader.load(plugin_dir)
                    plugin.source = "directory"
                    # Later directory sources override earlier (by name)
                    plugins[plugin.name] = plugin
                except (FileNotFoundError, ValueError):
                    # Skip invalid plugins
                    continue

        # 2. Entry point plugins (highest priority - override directory)
        entry_point_plugins = discover_from_entry_points()
        for name, plugin in entry_point_plugins.items():
            if name in plugins:
                _logger.debug(
                    "Entry point plugin '%s' overrides directory plugin",
                    name,
                )
            plugins[name] = plugin

        return plugins

    def discover_all(
        self,
        *,
        include_errors: bool = False,
    ) -> _typing.Iterator[manifest.Plugin | tuple[_pathlib.Path, Exception]]:
        """
        Discover all plugins, optionally including errors.

        This is an iterator that yields plugins as they're discovered,
        and optionally yields (path, exception) tuples for invalid plugins.

        Args:
            include_errors: If True, yield (path, exception) for failures.

        Yields:
            Plugin instances, or (path, exception) tuples if include_errors.
        """
        for search_path in self.get_search_paths():
            if not search_path.is_dir():
                continue

            for plugin_dir in sorted(search_path.iterdir()):
                if not plugin_dir.is_dir():
                    continue

                manifest_path = plugin_dir / "plugin.yaml"
                if not manifest_path.exists():
                    continue

                try:
                    plugin = self._loader.load(plugin_dir)
                    yield plugin
                except (FileNotFoundError, ValueError) as e:
                    if include_errors:
                        yield (plugin_dir, e)

