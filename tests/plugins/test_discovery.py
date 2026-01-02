"""
Tests for plugin discovery.

Tests verify that:
- Plugins are discovered from global, env, and project paths
- Later sources override earlier sources by name
- Invalid plugins are skipped
- Search path order is correct
"""

import os as _os
import pathlib as _pathlib
import unittest.mock as _mock

import brynhild.plugins.discovery as discovery


class TestPluginSearchPaths:
    """Tests for get_plugin_search_paths function."""

    def test_includes_global_path_first(self) -> None:
        """Global plugins path is always included first."""
        paths = discovery.get_plugin_search_paths()
        assert paths[0] == discovery.get_global_plugins_path()

    def test_includes_project_path_last(self, tmp_path: _pathlib.Path) -> None:
        """Project-local path is included last (highest priority)."""
        paths = discovery.get_plugin_search_paths(tmp_path)
        assert paths[-1] == discovery.get_project_plugins_path(tmp_path)

    def test_includes_env_paths_in_middle(self, tmp_path: _pathlib.Path) -> None:
        """BRYNHILD_PLUGIN_PATH env var paths are included."""
        env_path1 = tmp_path / "env1"
        env_path2 = tmp_path / "env2"
        env_path1.mkdir()
        env_path2.mkdir()

        with _mock.patch.dict(_os.environ, {"BRYNHILD_PLUGIN_PATH": f"{env_path1}:{env_path2}"}):
            paths = discovery.get_plugin_search_paths(tmp_path)

        # Global first, then env paths, then project last
        assert paths[0] == discovery.get_global_plugins_path()
        assert env_path1.resolve() in paths
        assert env_path2.resolve() in paths
        assert paths[-1] == discovery.get_project_plugins_path(tmp_path)

    def test_empty_env_path_is_ignored(self) -> None:
        """Empty BRYNHILD_PLUGIN_PATH doesn't add paths."""
        with _mock.patch.dict(_os.environ, {"BRYNHILD_PLUGIN_PATH": ""}):
            paths = discovery.get_plugin_search_paths()
        # Should just have global path
        assert len(paths) == 1

    def test_no_project_root_excludes_project_path(self) -> None:
        """Without project root, project path is not included."""
        paths = discovery.get_plugin_search_paths(project_root=None)
        for p in paths:
            assert ".brynhild/plugins" not in str(p)


class TestPluginDiscovery:
    """Tests for PluginDiscovery class."""

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

    def test_discovers_plugins_in_directory(self, tmp_path: _pathlib.Path) -> None:
        """Plugins in search path are discovered."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        self._create_plugin(plugins_dir, "plugin-a")
        self._create_plugin(plugins_dir, "plugin-b")

        disc = discovery.PluginDiscovery(search_paths=[plugins_dir])
        plugins = disc.discover()

        # Filter to directory-sourced plugins (ignore any globally installed entry point plugins)
        dir_plugins = {k: v for k, v in plugins.items() if v.source == "directory"}

        assert len(dir_plugins) == 2
        assert "plugin-a" in dir_plugins
        assert "plugin-b" in dir_plugins
        assert dir_plugins["plugin-a"].version == "1.0.0"
        assert dir_plugins["plugin-b"].version == "1.0.0"

    def test_later_sources_override_earlier_by_name(self, tmp_path: _pathlib.Path) -> None:
        """Plugin with same name from later source replaces earlier."""
        global_dir = tmp_path / "global"
        project_dir = tmp_path / "project"
        global_dir.mkdir()
        project_dir.mkdir()

        # Same plugin name, different versions
        self._create_plugin(global_dir, "shared-plugin", version="1.0.0")
        self._create_plugin(project_dir, "shared-plugin", version="2.0.0")

        # Global first, project last (higher priority)
        disc = discovery.PluginDiscovery(search_paths=[global_dir, project_dir])
        plugins = disc.discover()

        # Filter to directory-sourced plugins
        dir_plugins = {k: v for k, v in plugins.items() if v.source == "directory"}

        assert len(dir_plugins) == 1
        assert dir_plugins["shared-plugin"].version == "2.0.0"  # Project wins

    def test_skips_directories_without_manifest(self, tmp_path: _pathlib.Path) -> None:
        """Directories without plugin.yaml are skipped."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        self._create_plugin(plugins_dir, "valid-plugin")

        # Create directory without manifest
        (plugins_dir / "not-a-plugin").mkdir()
        (plugins_dir / "not-a-plugin" / "README.md").write_text("Not a plugin")

        disc = discovery.PluginDiscovery(search_paths=[plugins_dir])
        plugins = disc.discover()

        # Filter to directory-sourced plugins
        dir_plugins = {k: v for k, v in plugins.items() if v.source == "directory"}

        assert len(dir_plugins) == 1
        assert "valid-plugin" in dir_plugins
        assert "not-a-plugin" not in dir_plugins

    def test_skips_invalid_manifests(self, tmp_path: _pathlib.Path) -> None:
        """Plugins with invalid manifests are skipped."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        self._create_plugin(plugins_dir, "valid-plugin")

        # Create plugin with invalid manifest
        bad_plugin = plugins_dir / "bad-plugin"
        bad_plugin.mkdir()
        (bad_plugin / "plugin.yaml").write_text("invalid: {{ yaml")

        disc = discovery.PluginDiscovery(search_paths=[plugins_dir])
        plugins = disc.discover()

        # Filter to directory-sourced plugins
        dir_plugins = {k: v for k, v in plugins.items() if v.source == "directory"}

        assert len(dir_plugins) == 1
        assert "valid-plugin" in dir_plugins

    def test_skips_nonexistent_search_paths(self, tmp_path: _pathlib.Path) -> None:
        """Non-existent search paths are silently skipped."""
        existing = tmp_path / "existing"
        existing.mkdir()
        self._create_plugin(existing, "plugin")

        nonexistent = tmp_path / "nonexistent"  # Not created

        disc = discovery.PluginDiscovery(search_paths=[nonexistent, existing])
        plugins = disc.discover()

        # Filter to directory-sourced plugins
        dir_plugins = {k: v for k, v in plugins.items() if v.source == "directory"}

        assert len(dir_plugins) == 1
        assert "plugin" in dir_plugins

    def test_discover_all_yields_plugins(self, tmp_path: _pathlib.Path) -> None:
        """discover_all() yields Plugin objects."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        self._create_plugin(plugins_dir, "plugin-a")

        disc = discovery.PluginDiscovery(search_paths=[plugins_dir])
        results = list(disc.discover_all())

        # Should have at least one plugin result
        plugins = [r for r in results if not isinstance(r, Exception)]
        assert len(plugins) >= 1
        assert any(p.name == "plugin-a" for p in plugins)

    def test_discover_all_with_errors_yields_exceptions(self, tmp_path: _pathlib.Path) -> None:
        """discover_all() yields exceptions for invalid plugins when include_errors=True."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        # Create valid plugin
        self._create_plugin(plugins_dir, "valid-plugin")

        # Create invalid plugin (bad YAML)
        bad_plugin = plugins_dir / "bad-plugin"
        bad_plugin.mkdir()
        (bad_plugin / "plugin.yaml").write_text("invalid: {{ yaml")

        disc = discovery.PluginDiscovery(search_paths=[plugins_dir])
        results = list(disc.discover_all(include_errors=True))

        plugins = [r for r in results if not isinstance(r, tuple)]
        errors = [r for r in results if isinstance(r, tuple)]

        assert len(plugins) >= 1
        assert len(errors) >= 1


class TestHelperFunctions:
    """Tests for module-level helper functions."""

    def test_global_plugins_path_is_in_config(self) -> None:
        """Global plugins path is under ~/.config/brynhild."""
        path = discovery.get_global_plugins_path()
        assert ".config" in str(path) or "brynhild" in str(path)

    def test_project_plugins_path_is_in_brynhild(self, tmp_path: _pathlib.Path) -> None:
        """Project plugins path is .brynhild/plugins."""
        path = discovery.get_project_plugins_path(tmp_path)
        assert path == tmp_path / ".brynhild" / "plugins"
