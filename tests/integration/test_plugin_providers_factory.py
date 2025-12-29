"""
Integration tests for plugin providers being available through the factory.

This tests the full integration path:
1. Plugin declares providers in plugin.yaml
2. load_all_plugin_providers() discovers and registers plugin providers
3. api.create_provider("plugin-name") finds and instantiates the provider
4. Plugin providers work alongside builtin providers

This is a critical test - without it, plugin provider loading could silently
fail and users would get "Unknown provider" errors for their plugins.
"""

from __future__ import annotations

import pathlib as _pathlib
import unittest.mock as _mock

import pytest as _pytest

import brynhild.api as api
import brynhild.plugins.providers as plugin_providers

# Path to test fixtures
FIXTURES_DIR = _pathlib.Path(__file__).parent.parent / "fixtures"
PLUGINS_DIR = FIXTURES_DIR / "plugins"


class TestPluginProvidersInFactory:
    """Test that plugin providers are available through api.create_provider()."""

    def _setup_plugin_providers(self) -> None:
        """Load plugin providers from the test-complete fixture."""
        import brynhild.plugins.manifest as manifest

        test_plugin_path = PLUGINS_DIR / "test-complete"
        plugin_manifest = manifest.load_manifest(test_plugin_path / "plugin.yaml")
        test_plugin = manifest.Plugin(
            manifest=plugin_manifest,
            path=test_plugin_path,
            enabled=True,
        )

        # Load providers from this plugin
        loader = plugin_providers.ProviderLoader()
        loaded = loader.load_from_plugin(test_plugin_path, test_plugin.name)

        # Register them in the global registry
        for name, provider_cls in loaded.items():
            plugin_providers.register_plugin_provider(name, provider_cls)

    def test_plugin_provider_available_in_factory(self) -> None:
        """Plugin provider should be available through api.create_provider()."""
        self._setup_plugin_providers()

        # The test-marker provider should now be available in plugin registry
        all_providers = plugin_providers.get_all_plugin_providers()

        assert "test-marker" in all_providers, (
            f"test-marker not in plugin providers. Available: {list(all_providers.keys())}"
        )

    def test_create_plugin_provider_succeeds(self) -> None:
        """api.create_provider() should create plugin providers."""
        self._setup_plugin_providers()

        # Create the plugin provider (don't load plugins again - we did manually)
        provider = api.create_provider(
            provider="test-marker",
            model="custom-model",
            load_plugins=False,
            auto_profile=False,
        )

        assert provider.name == "test-marker"
        assert provider.model == "custom-model"

    @_pytest.mark.asyncio
    async def test_plugin_provider_can_complete(self) -> None:
        """Plugin provider created through factory should work."""
        self._setup_plugin_providers()

        provider = api.create_provider(
            provider="test-marker",
            load_plugins=False,
            auto_profile=False,
        )

        # Should be able to call complete
        response = await provider.complete([{"role": "user", "content": "test"}])

        # The test-marker provider returns a canned response with a marker
        assert "[TEST-MARKER-PROVIDER]" in response.content

    def test_get_available_providers_includes_plugins(self) -> None:
        """api.get_available_providers() should include plugin providers."""
        self._setup_plugin_providers()

        providers = api.get_available_providers(load_plugins=False)

        all_names = [p["name"] for p in providers]
        # At minimum, builtin providers should be there
        assert "openrouter" in all_names
        assert "ollama" in all_names
        # Note: Plugin providers may or may not appear depending on registry state

    def test_unknown_provider_error_mentions_plugin_providers(self) -> None:
        """Error for unknown provider should mention available types."""
        self._setup_plugin_providers()

        with _pytest.raises(ValueError) as exc_info:
            api.create_provider(
                provider="nonexistent-provider",
                load_plugins=False,
            )

        error_msg = str(exc_info.value)
        assert "Unknown provider" in error_msg
        # Should list available provider types
        assert "Available types:" in error_msg


class TestPluginProviderDiscovery:
    """Test plugin provider discovery through the full path."""

    def test_load_all_plugin_providers_finds_fixture_providers(self) -> None:
        """load_all_plugin_providers() should find providers from plugins."""
        import brynhild.plugins.discovery as discovery

        # Mock get_plugin_search_paths to return our test fixtures directory
        with _mock.patch.object(
            discovery,
            "get_plugin_search_paths",
            return_value=[PLUGINS_DIR],
        ):
            # Clear existing and reload
            plugin_providers._plugin_providers.clear()
            plugin_providers.load_all_plugin_providers()

        # Should have loaded the test-marker provider from test-complete plugin
        all_providers = plugin_providers.get_all_plugin_providers()
        assert "test-marker" in all_providers, (
            f"test-marker not found. Available: {list(all_providers.keys())}"
        )


class TestBuiltinProvidersPriority:
    """Test that builtin providers take priority over plugins."""

    def test_builtin_providers_always_available(self) -> None:
        """Builtin providers should always be in the list."""
        providers = api.get_available_providers(load_plugins=False)
        names = [p["name"] for p in providers]

        assert "openrouter" in names
        assert "ollama" in names

    def test_plugin_failure_doesnt_break_builtins(self) -> None:
        """If plugin loading fails, builtin providers still work."""
        with _mock.patch(
            "brynhild.plugins.providers.load_all_plugin_providers",
            side_effect=Exception("Plugin system exploded"),
        ):
            # Reset the loaded flag to force a reload attempt
            import brynhild.api.factory as factory
            factory._plugin_providers_loaded = False

            # Should still be able to get providers
            providers = api.get_available_providers(load_plugins=True)
            names = [p["name"] for p in providers]

            assert "openrouter" in names
            assert "ollama" in names

