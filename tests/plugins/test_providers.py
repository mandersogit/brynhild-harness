"""Tests for plugin provider loading functionality."""

import pathlib as _pathlib
import tempfile as _tempfile

import brynhild.plugins.manifest as manifest
import brynhild.plugins.providers as providers


class TestProviderManifest:
    """Tests for providers field in PluginManifest."""

    def test_manifest_providers_default_is_empty(self) -> None:
        """Default providers list should be empty."""
        m = manifest.PluginManifest(name="test", version="1.0.0")
        assert m.providers == []

    def test_manifest_accepts_providers_list(self) -> None:
        """Should accept a list of provider names."""
        m = manifest.PluginManifest(
            name="test",
            version="1.0.0",
            providers=["my-provider", "other-provider"],
        )
        assert m.providers == ["my-provider", "other-provider"]

    def test_plugin_has_providers_false_by_default(self) -> None:
        """Plugin.has_providers() should return False by default."""
        m = manifest.PluginManifest(name="test", version="1.0.0")
        p = manifest.Plugin(manifest=m, path=_pathlib.Path("/tmp/test"))
        assert p.has_providers() is False

    def test_plugin_has_providers_true_when_declared(self) -> None:
        """Plugin.has_providers() should return True when providers declared."""
        m = manifest.PluginManifest(
            name="test",
            version="1.0.0",
            providers=["my-provider"],
        )
        p = manifest.Plugin(manifest=m, path=_pathlib.Path("/tmp/test"))
        assert p.has_providers() is True

    def test_plugin_providers_path(self) -> None:
        """Plugin.providers_path should return path to providers/ directory."""
        m = manifest.PluginManifest(name="test", version="1.0.0")
        p = manifest.Plugin(manifest=m, path=_pathlib.Path("/tmp/test"))
        assert p.providers_path == _pathlib.Path("/tmp/test/providers")

    def test_plugin_to_dict_includes_providers(self) -> None:
        """Plugin.to_dict() should include providers."""
        m = manifest.PluginManifest(
            name="test",
            version="1.0.0",
            providers=["my-provider"],
        )
        p = manifest.Plugin(manifest=m, path=_pathlib.Path("/tmp/test"))
        d = p.to_dict()
        assert "providers" in d
        assert d["providers"] == ["my-provider"]


class TestProviderLoader:
    """Tests for ProviderLoader class."""

    def test_loader_starts_empty(self) -> None:
        """Loader should start with no loaded providers."""
        loader = providers.ProviderLoader()
        assert loader.get_loaded_providers() == {}

    def test_load_from_nonexistent_directory(self) -> None:
        """Loading from nonexistent directory should return empty dict."""
        loader = providers.ProviderLoader()
        result = loader.load_from_directory(_pathlib.Path("/nonexistent/path"))
        assert result == {}

    def test_load_from_empty_directory(self) -> None:
        """Loading from empty directory should return empty dict."""
        loader = providers.ProviderLoader()
        with _tempfile.TemporaryDirectory() as tmpdir:
            result = loader.load_from_directory(_pathlib.Path(tmpdir))
            assert result == {}

    def test_load_valid_provider_module(self) -> None:
        """Should load a valid provider module."""
        loader = providers.ProviderLoader()

        # Create a temporary provider module
        with _tempfile.TemporaryDirectory() as tmpdir:
            provider_file = _pathlib.Path(tmpdir) / "test_provider.py"
            provider_file.write_text('''
"""Test provider."""
import typing

class Provider:
    """Test LLM provider."""

    PROVIDER_NAME = "test"

    def __init__(self, model: str = "test-model", **kwargs: typing.Any) -> None:
        self._model = model

    @property
    def name(self) -> str:
        return "test"

    @property
    def model(self) -> str:
        return self._model

    def supports_tools(self) -> bool:
        return False

    async def complete(self, messages: list, **kwargs: typing.Any) -> dict:
        return {"content": "test"}

    async def stream(self, messages: list, **kwargs: typing.Any):
        yield {"type": "text", "text": "test"}
''')

            # Load the provider
            cls = loader.load_from_file(provider_file, "test-plugin")
            assert cls is not None
            assert hasattr(cls, "name")

            # Check it's in loaded providers
            loaded = loader.get_loaded_providers()
            assert "test_provider" in loaded or "test" in loaded


class TestProviderRegistry:
    """Tests for global provider registry functions."""

    def test_register_and_get_provider(self) -> None:
        """Should be able to register and retrieve a provider."""
        # Create a mock provider class
        class MockProvider:
            name = "mock"
            model = "mock-model"

            def complete(self) -> None:
                pass

        # Register it
        providers.register_plugin_provider("mock-test", MockProvider)

        # Retrieve it
        cls = providers.get_plugin_provider("mock-test")
        assert cls is MockProvider

    def test_get_nonexistent_provider_returns_none(self) -> None:
        """Getting nonexistent provider should return None."""
        result = providers.get_plugin_provider("nonexistent-provider-xyz")
        assert result is None

    def test_get_all_plugin_providers(self) -> None:
        """Should return dict of all registered providers."""
        # Register a test provider
        class TestProvider2:
            name = "test2"
            model = "test2-model"

            def complete(self) -> None:
                pass

        providers.register_plugin_provider("test-provider-2", TestProvider2)

        all_providers = providers.get_all_plugin_providers()
        assert isinstance(all_providers, dict)
        assert "test-provider-2" in all_providers


class TestIsProviderClass:
    """Tests for _is_provider_class helper."""

    def test_non_class_returns_false(self) -> None:
        """Non-class objects should return False."""
        assert providers._is_provider_class("string") is False
        assert providers._is_provider_class(123) is False
        assert providers._is_provider_class(None) is False

    def test_class_without_required_attrs_returns_false(self) -> None:
        """Class without name/model/complete should return False."""

        class BadProvider:
            pass

        assert providers._is_provider_class(BadProvider) is False

    def test_valid_provider_class_returns_true(self) -> None:
        """Valid provider class should return True."""

        class GoodProvider:
            name = "good"
            model = "good-model"

            def complete(self) -> None:
                pass

        assert providers._is_provider_class(GoodProvider) is True

    def test_provider_with_stream_returns_true(self) -> None:
        """Provider with stream instead of complete should return True."""

        class StreamProvider:
            name = "stream"
            model = "stream-model"

            def stream(self) -> None:
                pass

        assert providers._is_provider_class(StreamProvider) is True

