"""
Integration tests for entry point plugin discovery.

These tests verify end-to-end functionality with the test plugin
dynamically installed via the `installed_test_plugin` fixture.

The test plugin provides:
    - Plugin registration via brynhild.plugins entry point
    - TestCalculator tool via brynhild.tools entry point
"""

import pathlib as _pathlib

import brynhild.config as config
import brynhild.plugins.discovery as discovery
import brynhild.tools.registry as registry


class TestEntryPointPluginDiscovery:
    """Integration tests for entry point plugin discovery."""

    def test_discovers_installed_plugin_via_entry_point(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """The installed test plugin is discovered via entry points."""
        plugins = discovery.discover_from_entry_points()

        assert "test-plugin" in plugins
        plugin = plugins["test-plugin"]
        assert plugin.source == "entry_point"
        assert plugin.package_name == "brynhild-test-plugin"
        assert plugin.package_version == "0.0.1"
        assert plugin.manifest.name == "test-plugin"
        assert "TestCalculator" in plugin.manifest.tools

    def test_plugin_integrates_with_plugin_discovery_class(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """Entry point plugins merge correctly with directory plugins."""
        # Empty search paths = only entry points
        disc = discovery.PluginDiscovery(search_paths=[])
        plugins = disc.discover()

        assert "test-plugin" in plugins
        assert plugins["test-plugin"].source == "entry_point"


class TestEntryPointToolLoading:
    """Integration tests for loading tools via entry points."""

    def test_test_calculator_tool_loads(self, installed_test_plugin: _pathlib.Path) -> None:
        """The TestCalculator tool loads via entry points."""
        settings = config.Settings()
        tool_registry = registry.build_registry_from_settings(settings)

        # Tool should be registered
        assert "TestCalculator" in tool_registry

        tool = tool_registry.get("TestCalculator")
        assert tool is not None
        assert tool.name == "TestCalculator"
        assert "calculator" in tool.description.lower()

    async def test_test_calculator_tool_executes(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """The TestCalculator tool executes correctly."""
        settings = config.Settings()
        tool_registry = registry.build_registry_from_settings(settings)

        tool = tool_registry.get("TestCalculator")
        assert tool is not None

        # Execute the tool
        result = await tool.execute({"a": 10, "b": 5})

        assert result.success is True
        assert "15" in result.output  # 10 + 5 = 15

    async def test_test_calculator_tool_handles_errors(
        self, installed_test_plugin: _pathlib.Path
    ) -> None:
        """The TestCalculator tool handles invalid input."""
        settings = config.Settings()
        tool_registry = registry.build_registry_from_settings(settings)

        tool = tool_registry.get("TestCalculator")
        assert tool is not None

        # Missing required args
        result = await tool.execute({})

        assert result.success is False
        assert result.error is not None


class TestEntryPointPluginToolVerification:
    """Integration tests for the tool verification feature."""

    def test_declared_tool_is_loaded(self, installed_test_plugin: _pathlib.Path) -> None:
        """Tools declared in manifest are loaded via entry points."""
        # The test plugin declares TestCalculator in its manifest
        # AND registers it via brynhild.tools entry point
        settings = config.Settings()
        tool_registry = registry.build_registry_from_settings(settings)

        # Verify the tool from the manifest is actually loaded
        plugins = discovery.discover_from_entry_points()
        test_plugin = plugins.get("test-plugin")
        assert test_plugin is not None

        for declared_tool in test_plugin.manifest.tools:
            assert declared_tool in tool_registry, (
                f"Tool '{declared_tool}' declared in plugin manifest was not loaded into registry"
            )
