"""
Tests for entry point-based plugin discovery.

Tests verify that:
- Plugins can be discovered via 'brynhild.plugins' entry points
- Tools can be discovered via 'brynhild.tools' entry points
- Providers can be discovered via 'brynhild.providers' entry points
- Entry point plugins override directory plugins with same name
- Invalid entry points are logged but don't stop discovery
- Package metadata (name, version) is captured for entry point plugins

NOTE: Entry point discovery is disabled by default in tests. These tests
use the enable_entry_point_plugins fixture to re-enable it for testing.
"""

import pathlib as _pathlib
import unittest.mock as _mock

import pytest as _pytest

import brynhild.plugins.discovery as discovery
import brynhild.plugins.manifest as manifest
import brynhild.plugins.providers as providers
import brynhild.plugins.tools as tools

# Apply enable_entry_point_plugins fixture to all tests in this module
# NOTE: pytestmark must NOT have underscore prefix - it's a pytest convention
pytestmark = _pytest.mark.usefixtures("enable_entry_point_plugins")


class TestDiscoverFromEntryPoints:
    """Tests for discover_from_entry_points function."""

    def test_returns_empty_dict_when_no_entry_points(self) -> None:
        """Returns empty dict when no plugins are registered."""
        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[],
        ):
            result = discovery.discover_from_entry_points()

        assert result == {}

    def test_loads_plugin_from_entry_point(self) -> None:
        """Successfully loads plugin that returns PluginManifest."""
        # Create mock entry point
        mock_ep = _mock.Mock()
        mock_ep.name = "test-plugin"
        mock_ep.load.return_value = lambda: manifest.PluginManifest(
            name="test-plugin",
            version="1.0.0",
            description="A test plugin",
        )
        mock_ep.dist = _mock.Mock()
        mock_ep.dist.name = "brynhild-test-plugin"
        mock_ep.dist.version = "1.0.0"

        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        ):
            result = discovery.discover_from_entry_points()

        assert "test-plugin" in result
        plugin = result["test-plugin"]
        assert plugin.name == "test-plugin"
        assert plugin.version == "1.0.0"
        assert plugin.source == "entry_point"
        assert plugin.package_name == "brynhild-test-plugin"
        assert plugin.package_version == "1.0.0"

    def test_loads_plugin_returning_plugin_instance(self) -> None:
        """Successfully loads plugin that returns Plugin directly."""
        # Create a Plugin instance to return
        test_manifest = manifest.PluginManifest(
            name="direct-plugin",
            version="2.0.0",
        )
        test_plugin = manifest.Plugin(
            manifest=test_manifest,
            path=_pathlib.Path("/some/path"),
        )

        mock_ep = _mock.Mock()
        mock_ep.name = "direct-plugin"
        mock_ep.load.return_value = lambda: test_plugin
        mock_ep.dist = _mock.Mock()
        mock_ep.dist.name = "brynhild-direct"
        mock_ep.dist.version = "2.0.0"

        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        ):
            result = discovery.discover_from_entry_points()

        assert "direct-plugin" in result
        plugin = result["direct-plugin"]
        assert plugin.source == "entry_point"
        assert plugin.package_name == "brynhild-direct"

    def test_handles_invalid_return_type(self) -> None:
        """Logs warning for entry points returning invalid types."""
        mock_ep = _mock.Mock()
        mock_ep.name = "bad-plugin"
        mock_ep.load.return_value = lambda: "not a plugin"  # Invalid return
        mock_ep.dist = None

        def mock_entry_points(group: str) -> list:
            if group == "brynhild.plugins":
                return [mock_ep]
            return []  # No providers

        with _mock.patch(
            "importlib.metadata.entry_points",
            mock_entry_points,
        ):
            result = discovery.discover_from_entry_points()

        assert result == {}

    def test_handles_exception_during_load(self) -> None:
        """Logs warning when entry point loading fails."""
        mock_ep = _mock.Mock()
        mock_ep.name = "failing-plugin"
        mock_ep.load.side_effect = ImportError("Module not found")

        def mock_entry_points(group: str) -> list:
            if group == "brynhild.plugins":
                return [mock_ep]
            return []  # No providers

        with _mock.patch(
            "importlib.metadata.entry_points",
            mock_entry_points,
        ):
            result = discovery.discover_from_entry_points()

        # Should return empty, not raise
        assert result == {}

    def test_handles_missing_dist_attribute(self) -> None:
        """Handles entry points without dist metadata."""
        mock_ep = _mock.Mock()
        mock_ep.name = "no-dist-plugin"
        mock_ep.load.return_value = lambda: manifest.PluginManifest(
            name="no-dist-plugin",
            version="0.1.0",
        )
        mock_ep.dist = None

        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        ):
            result = discovery.discover_from_entry_points()

        plugin = result["no-dist-plugin"]
        assert plugin.package_name is None
        assert plugin.package_version is None


class TestPluginDiscoveryWithEntryPoints:
    """Tests for PluginDiscovery.discover() with entry points."""

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

    def test_entry_point_overrides_directory_plugin(self, tmp_path: _pathlib.Path) -> None:
        """Entry point plugin with same name overrides directory plugin."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        self._create_plugin(plugins_dir, "shared-plugin", version="1.0.0")

        # Create mock entry point with same name
        mock_ep = _mock.Mock()
        mock_ep.name = "shared-plugin"
        mock_ep.load.return_value = lambda: manifest.PluginManifest(
            name="shared-plugin",
            version="2.0.0",  # Different version
        )
        mock_ep.dist = _mock.Mock()
        mock_ep.dist.name = "brynhild-shared-plugin"
        mock_ep.dist.version = "2.0.0"

        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        ):
            disc = discovery.PluginDiscovery(search_paths=[plugins_dir])
            plugins = disc.discover()

        # Should have entry point version (2.0.0)
        assert len(plugins) == 1
        assert plugins["shared-plugin"].version == "2.0.0"
        assert plugins["shared-plugin"].source == "entry_point"

    def test_combines_directory_and_entry_point_plugins(self, tmp_path: _pathlib.Path) -> None:
        """Both directory and entry point plugins are discovered."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        self._create_plugin(plugins_dir, "dir-plugin")

        mock_ep = _mock.Mock()
        mock_ep.name = "ep-plugin"
        mock_ep.load.return_value = lambda: manifest.PluginManifest(
            name="ep-plugin",
            version="1.0.0",
        )
        mock_ep.dist = None

        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        ):
            disc = discovery.PluginDiscovery(search_paths=[plugins_dir])
            plugins = disc.discover()

        assert len(plugins) == 2
        assert "dir-plugin" in plugins
        assert "ep-plugin" in plugins
        assert plugins["dir-plugin"].source == "directory"
        assert plugins["ep-plugin"].source == "entry_point"


class TestDiscoverToolsFromEntryPoints:
    """Tests for discover_tools_from_entry_points function."""

    def test_returns_empty_dict_when_no_entry_points(self) -> None:
        """Returns empty dict when no tools are registered."""
        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[],
        ):
            result = tools.discover_tools_from_entry_points()

        assert result == {}

    def test_loads_valid_tool_class(self) -> None:
        """Successfully loads tool class from entry point."""

        # Create a minimal tool class
        class MockTool:
            _is_brynhild_duck_typed = True
            name = "MockTool"

            def execute(self) -> None:
                pass

        mock_ep = _mock.Mock()
        mock_ep.name = "mock-tool"
        mock_ep.load.return_value = MockTool
        mock_ep.dist = _mock.Mock()
        mock_ep.dist.name = "brynhild-mock-tool"

        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        ):
            result = tools.discover_tools_from_entry_points()

        assert "MockTool" in result
        assert result["MockTool"] is MockTool

    def test_skips_invalid_tool_class(self) -> None:
        """Skips entry points that aren't valid Tool classes."""

        class NotATool:
            pass  # Missing name and execute

        mock_ep = _mock.Mock()
        mock_ep.name = "not-a-tool"
        mock_ep.load.return_value = NotATool

        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        ):
            result = tools.discover_tools_from_entry_points()

        assert result == {}

    def test_handles_exception_during_load(self) -> None:
        """Handles exceptions when loading tool entry points."""
        mock_ep = _mock.Mock()
        mock_ep.name = "failing-tool"
        mock_ep.load.side_effect = ImportError("Module not found")

        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        ):
            result = tools.discover_tools_from_entry_points()

        assert result == {}


class TestDiscoverProvidersFromEntryPoints:
    """Tests for discover_providers_from_entry_points function."""

    def test_returns_empty_dict_when_no_entry_points(self) -> None:
        """Returns empty dict when no providers are registered."""
        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[],
        ):
            result = providers.discover_providers_from_entry_points()

        assert result == {}

    def test_loads_valid_provider_class(self) -> None:
        """Successfully loads provider class from entry point."""

        # Create a minimal provider class
        class MockProvider:
            _is_brynhild_duck_typed = True
            PROVIDER_NAME = "mock-provider"
            name = "mock-provider"
            model = "test-model"

            def complete(self) -> None:
                pass

        mock_ep = _mock.Mock()
        mock_ep.name = "mock-provider"
        mock_ep.load.return_value = MockProvider
        mock_ep.dist = _mock.Mock()
        mock_ep.dist.name = "brynhild-mock-provider"

        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        ):
            result = providers.discover_providers_from_entry_points()

        assert "mock-provider" in result
        assert result["mock-provider"] is MockProvider

    def test_uses_provider_name_class_attribute(self) -> None:
        """Uses PROVIDER_NAME class attribute for provider name."""

        class CustomNameProvider:
            _is_brynhild_duck_typed = True
            PROVIDER_NAME = "custom-name"
            name = "different"
            model = "test"

            def complete(self) -> None:
                pass

        mock_ep = _mock.Mock()
        mock_ep.name = "entry-point-name"
        mock_ep.load.return_value = CustomNameProvider
        mock_ep.dist = None

        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        ):
            result = providers.discover_providers_from_entry_points()

        # Should use PROVIDER_NAME, not entry point name
        assert "custom-name" in result
        assert "entry-point-name" not in result

    def test_falls_back_to_entry_point_name(self) -> None:
        """Falls back to entry point name if PROVIDER_NAME not defined."""

        class NoProviderNameProvider:
            _is_brynhild_duck_typed = True
            name = "provider"
            model = "test"

            def complete(self) -> None:
                pass

        mock_ep = _mock.Mock()
        mock_ep.name = "fallback-name"
        mock_ep.load.return_value = NoProviderNameProvider
        mock_ep.dist = None

        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        ):
            result = providers.discover_providers_from_entry_points()

        assert "fallback-name" in result

    def test_skips_invalid_provider_class(self) -> None:
        """Skips entry points that aren't valid Provider classes."""

        class NotAProvider:
            pass  # Missing required attributes

        mock_ep = _mock.Mock()
        mock_ep.name = "not-a-provider"
        mock_ep.load.return_value = NotAProvider

        with _mock.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        ):
            result = providers.discover_providers_from_entry_points()

        assert result == {}


class TestPluginMetadata:
    """Tests for Plugin dataclass entry point fields."""

    def test_plugin_source_default_is_directory(self) -> None:
        """Plugin.source defaults to 'directory'."""
        plugin = manifest.Plugin(
            manifest=manifest.PluginManifest(name="test", version="1.0.0"),
            path=_pathlib.Path("/test"),
        )
        assert plugin.source == "directory"
        assert plugin.package_name is None
        assert plugin.package_version is None

    def test_is_packaged_property(self) -> None:
        """Plugin.is_packaged returns True for entry_point source."""
        dir_plugin = manifest.Plugin(
            manifest=manifest.PluginManifest(name="dir", version="1.0.0"),
            path=_pathlib.Path("/test"),
            source="directory",
        )
        ep_plugin = manifest.Plugin(
            manifest=manifest.PluginManifest(name="ep", version="1.0.0"),
            path=_pathlib.Path("<entry-point>"),
            source="entry_point",
            package_name="brynhild-ep",
            package_version="1.0.0",
        )

        assert dir_plugin.is_packaged is False
        assert ep_plugin.is_packaged is True

    def test_to_dict_includes_entry_point_fields(self) -> None:
        """Plugin.to_dict includes source and package metadata."""
        plugin = manifest.Plugin(
            manifest=manifest.PluginManifest(name="test", version="1.0.0"),
            path=_pathlib.Path("<entry-point>"),
            source="entry_point",
            package_name="brynhild-test",
            package_version="2.0.0",
        )

        data = plugin.to_dict()

        assert data["source"] == "entry_point"
        assert data["package_name"] == "brynhild-test"
        assert data["package_version"] == "2.0.0"
