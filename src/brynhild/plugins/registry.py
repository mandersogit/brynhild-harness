"""
Plugin registry for tracking enabled/disabled state.

The registry persists enable/disable state to:
- ~/.config/brynhild/plugins.yaml (global state)

Plugin state is simple: enabled (default) or disabled.
"""

from __future__ import annotations

import pathlib as _pathlib
import typing as _typing

import yaml as _yaml

import brynhild.plugins.discovery as discovery
import brynhild.plugins.manifest as manifest


def get_registry_path() -> _pathlib.Path:
    """Get the path to the global plugin registry file."""
    return _pathlib.Path.home() / ".config" / "brynhild" / "plugins.yaml"


class PluginRegistry:
    """
    Registry for plugin enable/disable state.

    Tracks which plugins are enabled or disabled, persisting
    state to a YAML file.
    """

    def __init__(
        self,
        project_root: _pathlib.Path | None = None,
        registry_path: _pathlib.Path | None = None,
    ) -> None:
        """
        Initialize the plugin registry.

        Args:
            project_root: Project root for plugin discovery.
            registry_path: Path to registry file (defaults to global).
        """
        self._project_root = project_root
        self._registry_path = registry_path or get_registry_path()
        self._discovery = discovery.PluginDiscovery(project_root)

        # Load persisted state
        self._disabled: set[str] = set()
        self._load_state()

        # Cache of discovered plugins
        self._plugins: dict[str, manifest.Plugin] | None = None

    def _load_state(self) -> None:
        """Load enable/disable state from registry file."""
        if not self._registry_path.exists():
            return

        try:
            content = self._registry_path.read_text(encoding="utf-8")
            data = _yaml.safe_load(content) or {}
            disabled = data.get("disabled", [])
            if isinstance(disabled, list):
                self._disabled = set(disabled)
        except (OSError, _yaml.YAMLError):
            # Ignore invalid registry file
            pass

    def _save_state(self) -> None:
        """Save enable/disable state to registry file."""
        # Ensure parent directory exists
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "disabled": sorted(self._disabled),
        }
        content = _yaml.dump(data, default_flow_style=False)
        self._registry_path.write_text(content, encoding="utf-8")

    def _ensure_discovered(self) -> None:
        """Ensure plugins have been discovered."""
        if self._plugins is None:
            self._plugins = self._discovery.discover()
            # Apply enable/disable state
            for name, plugin in self._plugins.items():
                plugin.enabled = name not in self._disabled

    def discover(self) -> None:
        """Force re-discovery of plugins."""
        self._plugins = None
        self._ensure_discovered()

    def list_plugins(self) -> list[manifest.Plugin]:
        """
        List all discovered plugins.

        Returns:
            List of Plugin instances (with enabled state set).
        """
        self._ensure_discovered()
        assert self._plugins is not None
        return list(self._plugins.values())

    def get_plugin(self, name: str) -> manifest.Plugin | None:
        """
        Get a plugin by name.

        Args:
            name: Plugin name.

        Returns:
            Plugin instance or None if not found.
        """
        self._ensure_discovered()
        assert self._plugins is not None
        return self._plugins.get(name)

    def get_enabled_plugins(self) -> list[manifest.Plugin]:
        """
        Get all enabled plugins.

        Returns:
            List of enabled Plugin instances.
        """
        return [p for p in self.list_plugins() if p.enabled]

    def is_enabled(self, name: str) -> bool:
        """
        Check if a plugin is enabled.

        Args:
            name: Plugin name.

        Returns:
            True if enabled, False if disabled or not found.
        """
        plugin = self.get_plugin(name)
        return plugin is not None and plugin.enabled

    def enable(self, name: str) -> bool:
        """
        Enable a plugin.

        Args:
            name: Plugin name.

        Returns:
            True if state changed, False if already enabled or not found.
        """
        plugin = self.get_plugin(name)
        if plugin is None:
            return False

        if name not in self._disabled:
            return False  # Already enabled

        self._disabled.discard(name)
        plugin.enabled = True
        self._save_state()
        return True

    def disable(self, name: str) -> bool:
        """
        Disable a plugin.

        Args:
            name: Plugin name.

        Returns:
            True if state changed, False if already disabled or not found.
        """
        plugin = self.get_plugin(name)
        if plugin is None:
            return False

        if name in self._disabled:
            return False  # Already disabled

        self._disabled.add(name)
        plugin.enabled = False
        self._save_state()
        return True

    def to_dict(self) -> dict[str, _typing.Any]:
        """Convert registry state to dictionary for JSON serialization."""
        plugins = self.list_plugins()
        return {
            "plugins": [p.to_dict() for p in plugins],
            "enabled_count": len([p for p in plugins if p.enabled]),
            "disabled_count": len([p for p in plugins if not p.enabled]),
        }

