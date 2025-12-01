"""
Plugin discovery from standard locations.

Plugins are discovered from (in priority order):
1. ~/.config/brynhild/plugins/ - User plugins
2. $BRYNHILD_PLUGIN_PATH - Custom paths (colon-separated)
3. Project .brynhild/plugins/ - Project-local plugins

Later sources have higher priority (project overrides global).
"""

from __future__ import annotations

import os as _os
import pathlib as _pathlib
import typing as _typing

import brynhild.plugins.loader as loader
import brynhild.plugins.manifest as manifest


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
        Discover all plugins from search paths.

        Later sources override earlier sources (by plugin name).

        Returns:
            Dict mapping plugin name to Plugin instance.
        """
        plugins: dict[str, manifest.Plugin] = {}

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
                    # Later sources override earlier (by name)
                    plugins[plugin.name] = plugin
                except (FileNotFoundError, ValueError):
                    # Skip invalid plugins
                    continue

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

