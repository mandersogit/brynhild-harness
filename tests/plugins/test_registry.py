"""
Tests for plugin registry.

Tests verify that:
- Registry discovers and lists plugins
- Enable/disable state is tracked correctly
- State persists to registry file
- Enabled state is applied to discovered plugins
"""

import pathlib as _pathlib

import yaml as _yaml

import brynhild.plugins.registry as registry


class TestPluginRegistry:
    """Tests for PluginRegistry class."""

    def _create_plugin(
        self, parent: _pathlib.Path, name: str, version: str = "1.0.0"
    ) -> _pathlib.Path:
        """Helper to create a minimal plugin directory."""
        plugin_dir = parent / name
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.yaml").write_text(
            f"""
name: {name}
version: {version}
"""
        )
        return plugin_dir

    def test_lists_discovered_plugins(self, tmp_path: _pathlib.Path) -> None:
        """list_plugins returns all discovered plugins."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        self._create_plugin(plugins_dir, "plugin-a")
        self._create_plugin(plugins_dir, "plugin-b")

        # Use custom search paths and registry path
        reg = registry.PluginRegistry(
            registry_path=tmp_path / "registry.yaml",
        )
        # Override discovery to use our test directory
        reg._discovery._search_paths = [plugins_dir]
        reg._plugins = None  # Force rediscovery

        plugins = reg.list_plugins()

        # Filter to directory-sourced plugins (ignore any globally installed entry point plugins)
        dir_plugins = [p for p in plugins if p.source == "directory"]

        assert len(dir_plugins) == 2
        names = {p.name for p in dir_plugins}
        assert names == {"plugin-a", "plugin-b"}

    def test_get_plugin_by_name(self, tmp_path: _pathlib.Path) -> None:
        """get_plugin returns specific plugin by name."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        self._create_plugin(plugins_dir, "my-plugin", "2.0.0")

        reg = registry.PluginRegistry(registry_path=tmp_path / "registry.yaml")
        reg._discovery._search_paths = [plugins_dir]
        reg._plugins = None

        plugin = reg.get_plugin("my-plugin")

        assert plugin is not None
        assert plugin.name == "my-plugin"
        assert plugin.version == "2.0.0"

    def test_get_plugin_returns_none_for_unknown(self, tmp_path: _pathlib.Path) -> None:
        """get_plugin returns None for unknown plugin name."""
        reg = registry.PluginRegistry(registry_path=tmp_path / "registry.yaml")
        reg._discovery._search_paths = []  # No plugins
        reg._plugins = None

        assert reg.get_plugin("nonexistent") is None

    def test_plugins_enabled_by_default(self, tmp_path: _pathlib.Path) -> None:
        """Discovered plugins are enabled by default."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        self._create_plugin(plugins_dir, "plugin-a")

        reg = registry.PluginRegistry(registry_path=tmp_path / "registry.yaml")
        reg._discovery._search_paths = [plugins_dir]
        reg._plugins = None

        plugin = reg.get_plugin("plugin-a")

        assert plugin is not None
        assert plugin.enabled is True
        assert reg.is_enabled("plugin-a") is True

    def test_disable_marks_plugin_disabled(self, tmp_path: _pathlib.Path) -> None:
        """disable() marks plugin as disabled."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        self._create_plugin(plugins_dir, "plugin-a")

        reg = registry.PluginRegistry(registry_path=tmp_path / "registry.yaml")
        reg._discovery._search_paths = [plugins_dir]
        reg._plugins = None

        result = reg.disable("plugin-a")

        assert result is True  # State changed
        assert reg.is_enabled("plugin-a") is False
        plugin = reg.get_plugin("plugin-a")
        assert plugin is not None
        assert plugin.enabled is False

    def test_disable_returns_false_if_already_disabled(self, tmp_path: _pathlib.Path) -> None:
        """disable() returns False if plugin already disabled."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        self._create_plugin(plugins_dir, "plugin-a")

        reg = registry.PluginRegistry(registry_path=tmp_path / "registry.yaml")
        reg._discovery._search_paths = [plugins_dir]
        reg._plugins = None

        reg.disable("plugin-a")  # First disable
        result = reg.disable("plugin-a")  # Second disable

        assert result is False  # No state change

    def test_enable_marks_plugin_enabled(self, tmp_path: _pathlib.Path) -> None:
        """enable() marks previously disabled plugin as enabled."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        self._create_plugin(plugins_dir, "plugin-a")

        reg = registry.PluginRegistry(registry_path=tmp_path / "registry.yaml")
        reg._discovery._search_paths = [plugins_dir]
        reg._plugins = None

        reg.disable("plugin-a")
        result = reg.enable("plugin-a")

        assert result is True  # State changed
        assert reg.is_enabled("plugin-a") is True

    def test_enable_returns_false_if_already_enabled(self, tmp_path: _pathlib.Path) -> None:
        """enable() returns False if plugin already enabled."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        self._create_plugin(plugins_dir, "plugin-a")

        reg = registry.PluginRegistry(registry_path=tmp_path / "registry.yaml")
        reg._discovery._search_paths = [plugins_dir]
        reg._plugins = None

        result = reg.enable("plugin-a")  # Already enabled by default

        assert result is False  # No state change

    def test_disable_persists_to_file(self, tmp_path: _pathlib.Path) -> None:
        """Disabled state is persisted to registry file."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        self._create_plugin(plugins_dir, "plugin-a")
        registry_path = tmp_path / "registry.yaml"

        reg = registry.PluginRegistry(registry_path=registry_path)
        reg._discovery._search_paths = [plugins_dir]
        reg._plugins = None

        reg.disable("plugin-a")

        # Verify file content
        content = registry_path.read_text()
        data = _yaml.safe_load(content)
        assert "plugin-a" in data["disabled"]

    def test_disabled_state_loaded_on_init(self, tmp_path: _pathlib.Path) -> None:
        """Previously disabled state is loaded when registry is created."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        self._create_plugin(plugins_dir, "plugin-a")
        registry_path = tmp_path / "registry.yaml"

        # Pre-create registry file with disabled plugin
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text("disabled:\n  - plugin-a\n")

        reg = registry.PluginRegistry(registry_path=registry_path)
        reg._discovery._search_paths = [plugins_dir]
        reg._plugins = None

        assert reg.is_enabled("plugin-a") is False
        plugin = reg.get_plugin("plugin-a")
        assert plugin is not None
        assert plugin.enabled is False

    def test_get_enabled_plugins_filters_disabled(self, tmp_path: _pathlib.Path) -> None:
        """get_enabled_plugins returns only enabled plugins."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        self._create_plugin(plugins_dir, "enabled-plugin")
        self._create_plugin(plugins_dir, "disabled-plugin")

        reg = registry.PluginRegistry(registry_path=tmp_path / "registry.yaml")
        reg._discovery._search_paths = [plugins_dir]
        reg._plugins = None

        reg.disable("disabled-plugin")
        enabled = reg.get_enabled_plugins()

        assert len(enabled) == 1
        assert enabled[0].name == "enabled-plugin"

    def test_to_dict_includes_all_info(self, tmp_path: _pathlib.Path) -> None:
        """to_dict includes plugins and counts."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        self._create_plugin(plugins_dir, "plugin-a")
        self._create_plugin(plugins_dir, "plugin-b")

        reg = registry.PluginRegistry(registry_path=tmp_path / "registry.yaml")
        reg._discovery._search_paths = [plugins_dir]
        reg._plugins = None

        reg.disable("plugin-b")
        d = reg.to_dict()

        assert len(d["plugins"]) == 2
        assert d["enabled_count"] == 1
        assert d["disabled_count"] == 1

    def test_disable_unknown_plugin_returns_false(self, tmp_path: _pathlib.Path) -> None:
        """disable() returns False for unknown plugin."""
        reg = registry.PluginRegistry(registry_path=tmp_path / "registry.yaml")
        reg._discovery._search_paths = []
        reg._plugins = None

        result = reg.disable("nonexistent")

        assert result is False

    def test_enable_unknown_plugin_returns_false(self, tmp_path: _pathlib.Path) -> None:
        """enable() returns False for unknown plugin."""
        reg = registry.PluginRegistry(registry_path=tmp_path / "registry.yaml")
        reg._discovery._search_paths = []
        reg._plugins = None

        result = reg.enable("nonexistent")

        assert result is False

    def test_is_enabled_returns_false_for_unknown(self, tmp_path: _pathlib.Path) -> None:
        """is_enabled returns False for unknown plugin."""
        reg = registry.PluginRegistry(registry_path=tmp_path / "registry.yaml")
        reg._discovery._search_paths = []
        reg._plugins = None

        assert reg.is_enabled("nonexistent") is False
