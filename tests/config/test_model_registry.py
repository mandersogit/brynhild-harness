"""Tests for model registry integration.

Phase 5 tests:
- Registry loads and validates at startup
- Alias resolution works
- Native ID lookup works
- User can extend registry in their config
- Invalid registry entry fails with clear error
"""

import os as _os
import pathlib as _pathlib
import typing as _typing

import pydantic as _pydantic
import pytest as _pytest

import brynhild.config.settings as settings_module
import brynhild.config.types as types


@_pytest.fixture
def clean_env(monkeypatch: _pytest.MonkeyPatch) -> _typing.Generator[None, None, None]:
    """Clear all BRYNHILD env vars for isolated tests."""
    env_keys = [k for k in _os.environ if k.startswith("BRYNHILD")]
    for key in env_keys:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("BRYNHILD_SKIP_MIGRATION_CHECK", "1")
    yield


# =============================================================================
# ModelsConfig Tests
# =============================================================================


class TestModelsConfig:
    """Tests for ModelsConfig type."""

    def test_default_values(self) -> None:
        """ModelsConfig has sensible defaults."""
        config = types.ModelsConfig()

        assert config.default == "openai/gpt-oss-120b"
        assert config.favorites == {}
        assert config.aliases == {}
        assert config.registry == {}

    def test_favorites_with_bool_values(self) -> None:
        """Favorites can be simple True/False."""
        config = types.ModelsConfig(
            favorites={
                "model-a": True,
                "model-b": False,
            }
        )

        assert config.favorites["model-a"] is True
        assert config.favorites["model-b"] is False

    def test_favorites_with_dict_values(self) -> None:
        """Favorites can have metadata dicts."""
        config = types.ModelsConfig(
            favorites={
                "model-a": {"enabled": True, "priority": 1},
                "model-b": {"enabled": False},
            }
        )

        assert config.favorites["model-a"]["enabled"] is True
        assert config.favorites["model-a"]["priority"] == 1

    def test_aliases_map_to_canonical_ids(self) -> None:
        """Aliases are simple string mappings."""
        config = types.ModelsConfig(
            aliases={
                "sonnet": "anthropic/claude-sonnet-4",
                "llama": "meta-llama/llama-3.3-70b-instruct",
            }
        )

        assert config.aliases["sonnet"] == "anthropic/claude-sonnet-4"
        assert config.aliases["llama"] == "meta-llama/llama-3.3-70b-instruct"


class TestModelsConfigRegistry:
    """Tests for ModelsConfig.registry field validator."""

    def test_registry_converts_dicts_to_model_identity(self) -> None:
        """Raw dicts in registry are converted to ModelIdentity."""
        config = types.ModelsConfig(
            registry={
                "test/model": {
                    "bindings": {"openrouter": "test/model"},
                }
            }
        )

        identity = config.registry["test/model"]
        assert isinstance(identity, types.ModelIdentity)
        assert identity.canonical_id == "test/model"

    def test_registry_injects_canonical_id(self) -> None:
        """canonical_id is injected from the registry key."""
        config = types.ModelsConfig(
            registry={
                "injected/canonical-id": {
                    "bindings": {"provider": "native-id"},
                }
            }
        )

        identity = config.registry["injected/canonical-id"]
        assert identity.canonical_id == "injected/canonical-id"

    def test_registry_preserves_model_identity_objects(self) -> None:
        """ModelIdentity objects pass through unchanged."""
        original = types.ModelIdentity(
            canonical_id="original/id",
            bindings={"provider": "native"},
        )

        config = types.ModelsConfig(registry={"original/id": original})

        assert config.registry["original/id"] is original

    def test_registry_validates_descriptors(self) -> None:
        """Descriptor dicts are converted to ModelDescriptor."""
        config = types.ModelsConfig(
            registry={
                "test/model": {
                    "bindings": {"openrouter": "test/model"},
                    "descriptor": {
                        "family": "test",
                        "size": "7b",
                        "architecture": "dense",
                    },
                }
            }
        )

        identity = config.registry["test/model"]
        assert identity.descriptor is not None
        assert identity.descriptor.family == "test"
        assert identity.descriptor.size == "7b"
        assert identity.descriptor.architecture == "dense"

    def test_registry_invalid_entry_raises_error(self) -> None:
        """Invalid registry entry type raises clear error."""
        with _pytest.raises(_pydantic.ValidationError) as exc_info:
            types.ModelsConfig(
                registry={
                    "bad/entry": "not-a-dict-or-model-identity",
                }
            )

        # Check the error message is helpful
        assert "bad/entry" in str(exc_info.value)

    def test_registry_invalid_descriptor_raises_error(self) -> None:
        """Invalid descriptor fields raise validation error."""
        with _pytest.raises(_pydantic.ValidationError):
            types.ModelsConfig(
                registry={
                    "test/model": {
                        "descriptor": {
                            "family": "test",
                            "architecture": "invalid-arch",  # Must be "dense" or "moe"
                        },
                    }
                }
            )


# =============================================================================
# Settings Helper Methods Tests
# =============================================================================


class TestSettingsResolveModelAlias:
    """Tests for Settings.resolve_model_alias()."""

    def test_resolves_known_alias(self, clean_env: None) -> None:
        """Known aliases are resolved to canonical IDs."""
        settings = settings_module.Settings(_env_file=None)

        # Built-in alias from defaults/config.yaml
        result = settings.resolve_model_alias("opus")

        assert result == "anthropic/claude-opus-4.5"

    def test_returns_unchanged_for_unknown_alias(self, clean_env: None) -> None:
        """Unknown names are returned unchanged."""
        settings = settings_module.Settings(_env_file=None)

        result = settings.resolve_model_alias("not-an-alias")

        assert result == "not-an-alias"

    def test_canonical_id_returns_unchanged(self, clean_env: None) -> None:
        """Canonical IDs pass through unchanged."""
        settings = settings_module.Settings(_env_file=None)

        result = settings.resolve_model_alias("anthropic/claude-opus-4.5")

        assert result == "anthropic/claude-opus-4.5"


class TestSettingsGetModelIdentity:
    """Tests for Settings.get_model_identity()."""

    def test_returns_identity_for_known_model(self, clean_env: None) -> None:
        """Returns ModelIdentity for registered models."""
        settings = settings_module.Settings(_env_file=None)

        identity = settings.get_model_identity("anthropic/claude-opus-4.5")

        assert identity is not None
        assert identity.canonical_id == "anthropic/claude-opus-4.5"
        assert identity.descriptor is not None
        assert identity.descriptor.family == "claude"

    def test_returns_none_for_unknown_model(self, clean_env: None) -> None:
        """Returns None for models not in registry."""
        settings = settings_module.Settings(_env_file=None)

        identity = settings.get_model_identity("unknown/model")

        assert identity is None


class TestSettingsGetModelBinding:
    """Tests for Settings.get_model_binding()."""

    def test_returns_binding_for_default_provider(self, clean_env: None) -> None:
        """Returns binding for configured default provider."""
        settings = settings_module.Settings(_env_file=None)

        binding = settings.get_model_binding("anthropic/claude-opus-4.5")

        assert binding is not None
        assert binding.model_id == "anthropic/claude-opus-4.5"

    def test_returns_binding_for_specific_provider(self, clean_env: None) -> None:
        """Returns binding for explicitly specified provider."""
        settings = settings_module.Settings(_env_file=None)

        # Hermes has openrouter binding - test that specific provider lookup works
        binding = settings.get_model_binding(
            "nousresearch/hermes-4-70b",
            provider="openrouter",
        )

        assert binding is not None
        assert binding.model_id == "nousresearch/hermes-4-70b"

    def test_returns_none_for_unknown_model(self, clean_env: None) -> None:
        """Returns None for models not in registry."""
        settings = settings_module.Settings(_env_file=None)

        binding = settings.get_model_binding("unknown/model")

        assert binding is None

    def test_returns_none_for_unbound_provider(self, clean_env: None) -> None:
        """Returns None when model has no binding for provider."""
        settings = settings_module.Settings(_env_file=None)

        # Claude only has openrouter binding, not ollama
        binding = settings.get_model_binding(
            "anthropic/claude-opus-4.5",
            provider="ollama",
        )

        assert binding is None


class TestSettingsGetNativeModelId:
    """Tests for Settings.get_native_model_id()."""

    def test_returns_native_id_string(self, clean_env: None) -> None:
        """Returns just the model_id string, not full binding."""
        settings = settings_module.Settings(_env_file=None)

        native_id = settings.get_native_model_id(
            "nousresearch/hermes-4-70b",
            provider="openrouter",
        )

        assert native_id == "nousresearch/hermes-4-70b"
        assert isinstance(native_id, str)

    def test_returns_none_for_unknown(self, clean_env: None) -> None:
        """Returns None for unknown model/provider combinations."""
        settings = settings_module.Settings(_env_file=None)

        native_id = settings.get_native_model_id("unknown/model")

        assert native_id is None


class TestSettingsGetEffectiveContext:
    """Tests for Settings.get_effective_context()."""

    def test_returns_context_from_descriptor(self, clean_env: None) -> None:
        """Returns context_size from model descriptor."""
        settings = settings_module.Settings(_env_file=None)

        context = settings.get_effective_context("anthropic/claude-opus-4.5")

        assert context == 200000  # Claude Opus 4.5 context

    def test_returns_none_for_unknown_model(self, clean_env: None) -> None:
        """Returns None for unknown models."""
        settings = settings_module.Settings(_env_file=None)

        context = settings.get_effective_context("unknown/model")

        assert context is None


class TestSettingsGetFavorites:
    """Tests for Settings.get_favorites()."""

    def test_returns_list_of_favorite_ids(self, clean_env: None) -> None:
        """Returns list of canonical IDs marked as favorites."""
        settings = settings_module.Settings(_env_file=None)

        favorites = settings.get_favorites()

        assert isinstance(favorites, list)
        assert "openai/gpt-oss-120b" in favorites
        assert "anthropic/claude-opus-4.5" in favorites

    def test_includes_bool_true_favorites(
        self,
        clean_env: None,
        tmp_path: _pathlib.Path,
        monkeypatch: _pytest.MonkeyPatch,
    ) -> None:
        """Favorites with True value are included."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "config.yaml").write_text("""
models:
  favorites:
    enabled/model: true
    disabled/model: false
""")
        monkeypatch.setenv("BRYNHILD_CONFIG_DIR", str(config_dir))

        settings = settings_module.Settings(_env_file=None)
        favorites = settings.get_favorites()

        assert "enabled/model" in favorites
        assert "disabled/model" not in favorites

    def test_includes_dict_enabled_favorites(
        self,
        clean_env: None,
        tmp_path: _pathlib.Path,
        monkeypatch: _pytest.MonkeyPatch,
    ) -> None:
        """Favorites with dict value and enabled: true are included."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "config.yaml").write_text("""
models:
  favorites:
    explicit-enabled:
      enabled: true
      priority: 1
    explicit-disabled:
      enabled: false
    implicit-enabled:
      priority: 2
""")
        monkeypatch.setenv("BRYNHILD_CONFIG_DIR", str(config_dir))

        settings = settings_module.Settings(_env_file=None)
        favorites = settings.get_favorites()

        # Explicitly enabled
        assert "explicit-enabled" in favorites
        # Explicitly disabled (enabled: false)
        assert "explicit-disabled" not in favorites
        # Implicitly enabled (no enabled key defaults to True)
        assert "implicit-enabled" in favorites


# =============================================================================
# Registry Integration Tests
# =============================================================================


class TestRegistryLoadsAtStartup:
    """Tests that registry loads and validates during Settings construction."""

    def test_builtin_registry_loads(self, clean_env: None) -> None:
        """Built-in registry from defaults/config.yaml loads correctly."""
        settings = settings_module.Settings(_env_file=None)

        # Should have entries from defaults/config.yaml (8 models)
        assert len(settings.models.registry) >= 8

        # Spot-check known entries
        assert "openai/gpt-oss-120b" in settings.models.registry
        assert "anthropic/claude-opus-4.5" in settings.models.registry
        assert "google/gemini-3-flash-preview" in settings.models.registry

    def test_registry_entries_are_model_identity(self, clean_env: None) -> None:
        """All registry entries are validated ModelIdentity objects."""
        settings = settings_module.Settings(_env_file=None)

        for canonical_id, identity in settings.models.registry.items():
            assert isinstance(identity, types.ModelIdentity)
            assert identity.canonical_id == canonical_id

    def test_moe_model_has_active_size(
        self,
        clean_env: None,
        tmp_path: _pathlib.Path,
        monkeypatch: _pytest.MonkeyPatch,
    ) -> None:
        """MoE models have active_size in descriptor."""
        # Add a MoE model via user config
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "config.yaml").write_text("""
models:
  registry:
    test/moe-model:
      bindings:
        openrouter: test/moe-model
      descriptor:
        family: test
        size: 671b
        active_size: 37b
        architecture: moe
""")
        monkeypatch.setenv("BRYNHILD_CONFIG_DIR", str(config_dir))

        settings = settings_module.Settings(_env_file=None)

        moe_model = settings.models.registry.get("test/moe-model")
        assert moe_model is not None
        assert moe_model.descriptor is not None
        assert moe_model.descriptor.architecture == "moe"
        assert moe_model.descriptor.size == "671b"
        assert moe_model.descriptor.active_size == "37b"


class TestUserCanExtendRegistry:
    """Tests that users can add to the registry via config.

    Note: These tests use BRYNHILD_CONFIG_DIR to point to a custom config directory.
    This is the supported way to override config file locations in tests.
    """

    def test_user_registry_merged_with_builtin(
        self,
        clean_env: None,
        tmp_path: _pathlib.Path,
        monkeypatch: _pytest.MonkeyPatch,
    ) -> None:
        """User config can add new models to registry."""
        # Create user config directory with config.yaml
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        user_config = config_dir / "config.yaml"
        user_config.write_text("""
models:
  registry:
    custom/my-model:
      bindings:
        ollama: my-model:latest
      descriptor:
        family: custom
        size: 7b
""")

        # Point to user config directory
        monkeypatch.setenv("BRYNHILD_CONFIG_DIR", str(config_dir))

        settings = settings_module.Settings(_env_file=None)

        # Should have both builtin and user entries
        assert "openai/gpt-oss-120b" in settings.models.registry
        assert "custom/my-model" in settings.models.registry

        # User entry should be properly validated
        custom = settings.models.registry["custom/my-model"]
        assert isinstance(custom, types.ModelIdentity)
        assert custom.descriptor.family == "custom"

    def test_user_can_add_aliases(
        self,
        clean_env: None,
        tmp_path: _pathlib.Path,
        monkeypatch: _pytest.MonkeyPatch,
    ) -> None:
        """User config can add custom aliases."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        user_config = config_dir / "config.yaml"
        user_config.write_text("""
models:
  aliases:
    mymodel: custom/model-id
""")

        monkeypatch.setenv("BRYNHILD_CONFIG_DIR", str(config_dir))

        settings = settings_module.Settings(_env_file=None)

        # Should have both builtin and user aliases
        assert settings.models.aliases.get("opus") == "anthropic/claude-opus-4.5"
        assert settings.models.aliases.get("mymodel") == "custom/model-id"

    def test_user_can_override_builtin_registry_entry(
        self,
        clean_env: None,
        tmp_path: _pathlib.Path,
        monkeypatch: _pytest.MonkeyPatch,
    ) -> None:
        """User config can override builtin registry entries."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        user_config = config_dir / "config.yaml"
        user_config.write_text("""
models:
  registry:
    anthropic/claude-opus-4.5:
      bindings:
        openrouter: anthropic/claude-opus-4.5
        ollama: claude-opus-local:latest
      descriptor:
        family: claude
        series: opus-4.5
        context_size: 200000
""")

        monkeypatch.setenv("BRYNHILD_CONFIG_DIR", str(config_dir))

        settings = settings_module.Settings(_env_file=None)

        # User's version should have ollama binding
        identity = settings.models.registry["anthropic/claude-opus-4.5"]
        ollama_binding = identity.get_binding("ollama")
        assert ollama_binding is not None
        assert ollama_binding.model_id == "claude-opus-local:latest"


class TestInvalidRegistryFailsFast:
    """Tests that invalid registry entries cause startup failure."""

    def test_invalid_descriptor_architecture_fails(
        self,
        clean_env: None,
        tmp_path: _pathlib.Path,
        monkeypatch: _pytest.MonkeyPatch,
    ) -> None:
        """Invalid architecture value fails at startup."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        user_config = config_dir / "config.yaml"
        user_config.write_text("""
models:
  registry:
    bad/model:
      descriptor:
        family: test
        architecture: transformer
""")

        monkeypatch.setenv("BRYNHILD_CONFIG_DIR", str(config_dir))

        with _pytest.raises(_pydantic.ValidationError):
            settings_module.Settings(_env_file=None)

    def test_invalid_registry_entry_type_fails(
        self,
        clean_env: None,
        tmp_path: _pathlib.Path,
        monkeypatch: _pytest.MonkeyPatch,
    ) -> None:
        """Non-dict registry entry fails at startup."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        user_config = config_dir / "config.yaml"
        user_config.write_text("""
models:
  registry:
    bad/entry: "just a string"
""")

        monkeypatch.setenv("BRYNHILD_CONFIG_DIR", str(config_dir))

        with _pytest.raises(_pydantic.ValidationError):
            settings_module.Settings(_env_file=None)
