"""
Integration tests for plugin tools being loaded into the tool registry.

This tests the full integration path:
1. Plugin declares tools in plugin.yaml
2. build_registry_from_settings() discovers and loads plugin tools
3. Plugin tools are available alongside builtin tools
4. Plugin tools can be executed through the registry

This is a critical test - without it, the plugin tool loading could silently
fail and users would never see their custom tools.
"""

from __future__ import annotations

import pathlib as _pathlib
import unittest.mock as _mock

import pytest as _pytest

import brynhild.config as config
import brynhild.tools.registry as registry

# Path to test fixtures
FIXTURES_DIR = _pathlib.Path(__file__).parent.parent / "fixtures"
PLUGINS_DIR = FIXTURES_DIR / "plugins"


def _create_settings_with_project_root(project_root: _pathlib.Path) -> config.Settings:
    """Create settings with a specific project root by mocking find_project_root."""
    with _mock.patch(
        "brynhild.config.settings.find_project_root",
        return_value=project_root,
    ):
        return config.Settings(_env_file=None)


def _create_mock_plugin_registry(plugins: list) -> _mock.MagicMock:  # type: ignore[type-arg]
    """Create a mock PluginRegistry that returns the given plugins."""
    mock_registry = _mock.MagicMock()
    mock_registry.get_enabled_plugins.return_value = plugins
    return mock_registry


class TestPluginToolsLoadedIntoRegistry:
    """Test that plugin tools are loaded into the tool registry."""

    def test_plugin_tools_loaded_from_settings(self, tmp_path: _pathlib.Path) -> None:
        """Plugin tools should be loaded when build_registry_from_settings is called."""
        import brynhild.plugins.manifest as manifest

        # Create test plugin reference
        test_plugin_path = PLUGINS_DIR / "test-complete"
        plugin_manifest = manifest.load_manifest(test_plugin_path / "plugin.yaml")
        test_plugin = manifest.Plugin(
            manifest=plugin_manifest,
            path=test_plugin_path,
            enabled=True,
        )

        # Create settings with tmp_path as project root
        settings = _create_settings_with_project_root(tmp_path)

        # Mock the plugin registry to return our test plugin
        with _mock.patch(
            "brynhild.plugins.registry.PluginRegistry",
            return_value=_create_mock_plugin_registry([test_plugin]),
        ):
            tool_registry = registry.build_registry_from_settings(settings)

        # Verify the marker tool from the plugin is registered
        assert "marker" in tool_registry, (
            f"Plugin tool 'marker' not found in registry. "
            f"Available tools: {tool_registry.list_names()}"
        )

        # Verify builtin tools are still there
        assert "Bash" in tool_registry
        assert "Read" in tool_registry
        assert "Write" in tool_registry

    @_pytest.mark.asyncio
    async def test_plugin_tool_can_execute(self, tmp_path: _pathlib.Path) -> None:
        """Plugin tools loaded into registry should be executable."""
        import brynhild.plugins.manifest as manifest

        test_plugin_path = PLUGINS_DIR / "test-complete"
        plugin_manifest = manifest.load_manifest(test_plugin_path / "plugin.yaml")
        test_plugin = manifest.Plugin(
            manifest=plugin_manifest,
            path=test_plugin_path,
            enabled=True,
        )

        settings = _create_settings_with_project_root(tmp_path)

        with _mock.patch(
            "brynhild.plugins.registry.PluginRegistry",
            return_value=_create_mock_plugin_registry([test_plugin]),
        ):
            tool_registry = registry.build_registry_from_settings(settings)

        # Get the marker tool and execute it
        marker_tool = tool_registry.get("marker")
        assert marker_tool is not None, "marker tool not found in registry"

        result = await marker_tool.execute(message="integration test")

        assert result["success"] is True
        assert "[PLUGIN-TOOL-MARKER]" in result["output"]
        assert "integration test" in result["output"]

    def test_plugin_tools_appear_in_api_format(self, tmp_path: _pathlib.Path) -> None:
        """Plugin tools should appear in to_api_format() output (for system prompt)."""
        import brynhild.plugins.manifest as manifest

        test_plugin_path = PLUGINS_DIR / "test-complete"
        plugin_manifest = manifest.load_manifest(test_plugin_path / "plugin.yaml")
        test_plugin = manifest.Plugin(
            manifest=plugin_manifest,
            path=test_plugin_path,
            enabled=True,
        )

        settings = _create_settings_with_project_root(tmp_path)

        with _mock.patch(
            "brynhild.plugins.registry.PluginRegistry",
            return_value=_create_mock_plugin_registry([test_plugin]),
        ):
            tool_registry = registry.build_registry_from_settings(settings)

        # Get API format (used for system prompt)
        api_tools = tool_registry.to_api_format()
        tool_names = [t["name"] for t in api_tools]

        assert "marker" in tool_names, (
            f"Plugin tool 'marker' not in API format output. Tools: {tool_names}"
        )

    def test_plugin_tools_appear_in_openai_format(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """Plugin tools should appear in to_openai_format() output."""
        import brynhild.plugins.manifest as manifest

        test_plugin_path = PLUGINS_DIR / "test-complete"
        plugin_manifest = manifest.load_manifest(test_plugin_path / "plugin.yaml")
        test_plugin = manifest.Plugin(
            manifest=plugin_manifest,
            path=test_plugin_path,
            enabled=True,
        )

        settings = _create_settings_with_project_root(tmp_path)

        with _mock.patch(
            "brynhild.plugins.registry.PluginRegistry",
            return_value=_create_mock_plugin_registry([test_plugin]),
        ):
            tool_registry = registry.build_registry_from_settings(settings)

        # Get OpenAI format (used for OpenRouter)
        openai_tools = tool_registry.to_openai_format()
        tool_names = [t["function"]["name"] for t in openai_tools]

        assert "marker" in tool_names, (
            f"Plugin tool 'marker' not in OpenAI format output. Tools: {tool_names}"
        )


class TestPluginToolsErrorHandling:
    """Test error handling when loading plugin tools."""

    def test_builtin_tools_work_when_plugins_fail(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """Builtin tools should still be available if plugin loading fails."""
        settings = _create_settings_with_project_root(tmp_path)

        # Make plugin registry raise an exception
        with _mock.patch(
            "brynhild.plugins.registry.PluginRegistry",
            side_effect=Exception("Plugin system crashed"),
        ):
            tool_registry = registry.build_registry_from_settings(settings)

        # Builtin tools should still be available
        assert "Bash" in tool_registry
        assert "Read" in tool_registry
        assert "Write" in tool_registry
        assert "Edit" in tool_registry

    def test_other_plugins_load_when_one_fails(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """If one plugin's tools fail to load, other plugins should still work."""
        import brynhild.plugins.manifest as manifest

        # Create a working plugin
        test_plugin_path = PLUGINS_DIR / "test-complete"
        plugin_manifest = manifest.load_manifest(test_plugin_path / "plugin.yaml")
        working_plugin = manifest.Plugin(
            manifest=plugin_manifest,
            path=test_plugin_path,
            enabled=True,
        )

        # Create a broken plugin (points to nonexistent path)
        broken_manifest = manifest.PluginManifest(
            name="broken",
            version="1.0.0",
            tools=["nonexistent"],
        )
        broken_plugin = manifest.Plugin(
            manifest=broken_manifest,
            path=tmp_path / "nonexistent-plugin",
            enabled=True,
        )

        settings = _create_settings_with_project_root(tmp_path)

        # Return broken plugin first, then working plugin
        with _mock.patch(
            "brynhild.plugins.registry.PluginRegistry",
            return_value=_create_mock_plugin_registry([broken_plugin, working_plugin]),
        ):
            tool_registry = registry.build_registry_from_settings(settings)

        # The working plugin's tool should be loaded
        assert "marker" in tool_registry, (
            f"Working plugin tool 'marker' should be loaded. "
            f"Available: {tool_registry.list_names()}"
        )


class TestDisabledPluginTools:
    """Test that disabled plugins don't have their tools loaded."""

    def test_disabled_plugin_tools_not_loaded(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """Tools from disabled plugins should not be loaded."""
        settings = _create_settings_with_project_root(tmp_path)

        # get_enabled_plugins returns empty list since all plugins are disabled
        with _mock.patch(
            "brynhild.plugins.registry.PluginRegistry",
            return_value=_create_mock_plugin_registry([]),
        ):
            tool_registry = registry.build_registry_from_settings(settings)

        # Plugin tool should NOT be present
        assert "marker" not in tool_registry
        # But builtin tools should still be there
        assert "Bash" in tool_registry


class TestNoPluginsScenario:
    """Test behavior when no plugins are present."""

    def test_registry_works_with_no_plugins(self, tmp_path: _pathlib.Path) -> None:
        """Registry should still work normally when no plugins exist."""
        settings = _create_settings_with_project_root(tmp_path)

        with _mock.patch(
            "brynhild.plugins.registry.PluginRegistry",
            return_value=_create_mock_plugin_registry([]),
        ):
            tool_registry = registry.build_registry_from_settings(settings)

        # Should have all builtin tools
        assert len(tool_registry) == len(registry.BUILTIN_TOOL_NAMES)
        for tool_name in registry.BUILTIN_TOOL_NAMES:
            assert tool_name in tool_registry
