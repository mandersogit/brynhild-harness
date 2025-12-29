"""
Tests for provider instance configuration.

Verifies that:
- Provider instances can be configured with explicit type fields
- Custom instance names (like ollama-behemoth) work with type dispatch
- Legacy configs without type field are detected and rejected
- Factory uses type field for provider creation
"""

from __future__ import annotations

import os as _os
import tempfile as _tempfile
import unittest.mock as _mock

import pydantic as _pydantic
import pytest as _pytest

import brynhild.api as api
import brynhild.config.types as types


class TestProviderInstanceConfig:
    """Specification tests for ProviderInstanceConfig schema.

    These tests fully specify the behavior of ProviderInstanceConfig:
    - type field is required (not optional)
    - type field is accessible after creation
    - extra fields are preserved for provider-specific config
    """

    def test_type_field_required(self) -> None:
        """ProviderInstanceConfig must require type field.

        Requirement: All provider instances must declare their type explicitly.
        Fails if: type field becomes optional or has a default.
        """
        with _pytest.raises(_pydantic.ValidationError) as exc_info:
            types.ProviderInstanceConfig()
        assert "type" in str(exc_info.value)

    def test_type_field_stored(self) -> None:
        """Type field must be accessible on the config object.

        Requirement: Factory needs to read type to dispatch correctly.
        Fails if: type field not stored or renamed.
        """
        config = types.ProviderInstanceConfig(type="ollama")
        assert config.type == "ollama"

    def test_extra_fields_preserved(self) -> None:
        """Provider-specific fields must be preserved in model_extra."""
        config = types.ProviderInstanceConfig(
            type="openrouter",
            api_version="2024-01",
            custom_setting="value",
        )
        assert config.type == "openrouter"
        assert config.model_extra is not None
        assert config.model_extra.get("api_version") == "2024-01"
        assert config.model_extra.get("custom_setting") == "value"


class TestProvidersConfigInstances:
    """Tests for ProvidersConfig.instances structure."""

    def test_instances_with_type_field(self) -> None:
        """Instances with type field should be valid."""
        data = {
            "default": "my-ollama",
            "instances": {
                "my-ollama": {
                    "type": "ollama",
                    "base_url": "http://gpu-server:11434",
                },
                "openrouter": {
                    "type": "openrouter",
                },
            },
        }
        config = types.ProvidersConfig.model_validate(data)
        assert config.default == "my-ollama"
        assert "my-ollama" in config.instances
        assert config.instances["my-ollama"].type == "ollama"
        assert config.instances["my-ollama"].base_url == "http://gpu-server:11434"

    def test_legacy_format_without_type_raises_error(self) -> None:
        """Legacy config without type field should raise error."""
        data = {
            "default": "ollama",
            "ollama": {
                "base_url": "http://localhost:11434",
            },
        }
        with _pytest.raises(ValueError) as exc_info:
            types.ProvidersConfig.model_validate(data)
        assert "Legacy provider config detected" in str(exc_info.value)
        assert "type" in str(exc_info.value)

    def test_legacy_detection_message_helpful(self) -> None:
        """Legacy detection error should provide helpful migration guidance."""
        data = {
            "default": "openrouter",
            "openrouter": {"enabled": True},
        }
        with _pytest.raises(ValueError) as exc_info:
            types.ProvidersConfig.model_validate(data)
        error_msg = str(exc_info.value)
        # Should mention what's wrong
        assert "Legacy provider config detected" in error_msg
        # Should show the fix
        assert "type: openrouter" in error_msg or "type:" in error_msg

    def test_get_provider_config_returns_typed_instance(self) -> None:
        """get_provider_config should return typed ProviderInstanceConfig."""
        data = {
            "instances": {
                "ollama-behemoth": {
                    "type": "ollama",
                    "base_url": "http://behemoth:11434",
                },
            },
        }
        config = types.ProvidersConfig.model_validate(data)
        instance = config.get_provider_config("ollama-behemoth")
        assert instance is not None
        assert isinstance(instance, types.ProviderInstanceConfig)
        assert instance.type == "ollama"

    def test_get_provider_config_missing_returns_none(self) -> None:
        """get_provider_config should return None for unknown provider."""
        config = types.ProvidersConfig()
        result = config.get_provider_config("nonexistent")
        assert result is None


class TestFactoryTypeDispatch:
    """Tests for factory type-based dispatch."""

    def test_factory_reads_type_from_config(self) -> None:
        """Factory should read type field and use correct provider."""
        # Create a temp config with a custom ollama instance
        config_yaml = """
providers:
  default: ollama-test
  instances:
    ollama-test:
      type: ollama
      base_url: http://test-server:11434
"""
        with _tempfile.TemporaryDirectory() as tmp_dir:
            config_path = _os.path.join(tmp_dir, "config.yaml")
            with open(config_path, "w") as f:
                f.write(config_yaml)

            # Clear env vars that would override the base_url
            clean_env = {
                k: v
                for k, v in _os.environ.items()
                if k not in ("OLLAMA_HOST", "BRYNHILD_OLLAMA_HOST")
            }
            clean_env["BRYNHILD_CONFIG_DIR"] = tmp_dir

            with _mock.patch.dict(_os.environ, clean_env, clear=True):
                # This should use ollama provider type for "ollama-test" instance
                provider = api.create_provider(
                    provider="ollama-test",
                    model="llama3",
                    auto_profile=False,
                )
                # Should be an Ollama provider
                assert provider.name == "ollama"
                # Should have the custom base URL parsed
                assert "test-server" in provider.base_url

    def test_factory_falls_back_to_builtin_types(self) -> None:
        """Factory should fall back to builtin types if no config."""
        # When provider name matches a builtin type, should work without config
        provider = api.create_provider(
            provider="openrouter",
            model="openai/gpt-oss-120b",
            auto_profile=False,
        )
        assert provider.name == "openrouter"

    def test_factory_unknown_provider_clear_error(self) -> None:
        """Factory should give clear error for unknown provider."""
        with _pytest.raises(ValueError) as exc_info:
            api.create_provider(
                provider="nonexistent-provider-xyz",
                auto_profile=False,
            )
        error_msg = str(exc_info.value)
        assert "Unknown provider" in error_msg
        assert "providers.instances" in error_msg or "Available types" in error_msg

    def test_factory_stub_provider_raises_not_implemented(self) -> None:
        """Stub providers should raise NotImplementedError."""
        # Create a config that declares a vllm instance
        config_yaml = """
providers:
  default: vllm-test
  instances:
    vllm-test:
      type: vllm
      base_url: http://vllm-server:8000
"""
        with _tempfile.TemporaryDirectory() as tmp_dir:
            config_path = _os.path.join(tmp_dir, "config.yaml")
            with open(config_path, "w") as f:
                f.write(config_yaml)

            with _mock.patch.dict(
                _os.environ,
                {"BRYNHILD_CONFIG_DIR": tmp_dir},
                clear=False,
            ):
                with _pytest.raises(NotImplementedError) as exc_info:
                    api.create_provider(
                        provider="vllm-test",
                        auto_profile=False,
                    )
                error_msg = str(exc_info.value)
                assert "vLLM" in error_msg or "not yet implemented" in error_msg


class TestProviderTypesRegistry:
    """Invariant guards for provider type registry.

    These tests guard the requirement that specific provider types must be
    available in the registry. They catch accidental removals or import errors
    that would break the provider system.
    """

    def test_get_available_provider_types(self) -> None:
        """Registry must include all supported provider types.

        Guards: Provider type registry completeness.
        Fails if: A supported type is accidentally removed or import fails.
        """
        types_set = api.get_available_provider_types()
        assert "ollama" in types_set
        assert "openrouter" in types_set
        # Stub types should be available too
        assert "vllm" in types_set
        assert "lmstudio" in types_set
        assert "openai" in types_set

    def test_get_available_provider_names_includes_configured(self) -> None:
        """Default config instances must appear in available names.

        Guards: Config-to-registry integration.
        Fails if: Default config instances aren't being loaded.
        """
        names = api.get_available_provider_names()
        assert "openrouter" in names
        assert "ollama" in names

    def test_get_available_providers_info(self) -> None:
        """Provider info must include type field after Phase 5 changes.

        Guards: API contract for get_available_providers().
        Fails if: Provider info dict missing required fields.
        """
        providers = api.get_available_providers()
        openrouter_info = next(
            (p for p in providers if p["name"] == "openrouter"), None
        )
        assert openrouter_info is not None
        assert openrouter_info["type"] == "openrouter"
        assert openrouter_info["available"] is True


class TestDefaultsConfigProviders:
    """Specification tests for defaults/config.yaml provider requirements.

    These tests encode requirements for the shipped default configuration.
    They serve as executable documentation of what must be present in the
    default config file for brynhild to work out-of-the-box.
    """

    def test_default_config_has_instances(self) -> None:
        """Default config must have at least one provider instance.

        Requirement: Users should have working providers without any config.
        Fails if: defaults/config.yaml is missing providers.instances section.
        """
        import brynhild.config as config

        settings = config.Settings()
        assert hasattr(settings.providers, "instances")
        assert len(settings.providers.instances) > 0

    def test_default_config_instances_have_type(self) -> None:
        """All provider instances in defaults must have explicit type field.

        Requirement: Phase 5 mandates type field on all provider instances.
        Fails if: Any instance in defaults/config.yaml is missing type.
        """
        import brynhild.config as config

        settings = config.Settings()
        for name, instance in settings.providers.instances.items():
            assert instance.type is not None, f"Instance {name} missing type"
            assert isinstance(instance.type, str), f"Instance {name} type not string"

    def test_default_config_openrouter_instance(self) -> None:
        """Default config must include openrouter (primary cloud provider).

        Requirement: OpenRouter is the default/recommended provider.
        Fails if: openrouter instance accidentally removed from defaults.
        """
        import brynhild.config as config

        settings = config.Settings()
        openrouter = settings.providers.get_provider_config("openrouter")
        assert openrouter is not None
        assert openrouter.type == "openrouter"

    def test_default_config_ollama_instance(self) -> None:
        """Default config must include ollama (primary local provider).

        Requirement: Ollama is the default local/private provider option.
        Fails if: ollama instance accidentally removed from defaults.
        """
        import brynhild.config as config

        settings = config.Settings()
        ollama = settings.providers.get_provider_config("ollama")
        assert ollama is not None
        assert ollama.type == "ollama"


class TestProviderInstanceEdgeCases:
    """Edge case tests for provider instance configuration."""

    def test_empty_type_string_rejected(self) -> None:
        """Empty string type should be rejected by factory as invalid."""
        # Create a config with empty type string
        config_yaml = """
providers:
  default: empty-type-provider
  instances:
    empty-type-provider:
      type: ""
"""
        with _tempfile.TemporaryDirectory() as tmp_dir:
            config_path = _os.path.join(tmp_dir, "config.yaml")
            with open(config_path, "w") as f:
                f.write(config_yaml)

            with _mock.patch.dict(
                _os.environ,
                {"BRYNHILD_CONFIG_DIR": tmp_dir},
                clear=False,
            ):
                # Factory should fail when trying to use the empty type
                with _pytest.raises(ValueError) as exc_info:
                    api.create_provider(
                        provider="empty-type-provider",
                        auto_profile=False,
                    )
                # Error should mention the type problem
                error_msg = str(exc_info.value)
                assert "Unknown provider type" in error_msg or "type" in error_msg.lower()

    def test_unknown_type_gives_helpful_error(self) -> None:
        """Completely unknown type (not a stub) should give clear error."""
        config_yaml = """
providers:
  default: my-fake
  instances:
    my-fake:
      type: nonexistent_provider_type_xyz
"""
        with _tempfile.TemporaryDirectory() as tmp_dir:
            config_path = _os.path.join(tmp_dir, "config.yaml")
            with open(config_path, "w") as f:
                f.write(config_yaml)

            with _mock.patch.dict(
                _os.environ,
                {"BRYNHILD_CONFIG_DIR": tmp_dir},
                clear=False,
            ):
                with _pytest.raises((ValueError, NotImplementedError)) as exc_info:
                    api.create_provider(
                        provider="my-fake",
                        auto_profile=False,
                    )
                error_msg = str(exc_info.value)
                # Should mention what types ARE available
                assert "ollama" in error_msg.lower() or "available" in error_msg.lower()

    def test_multiple_instances_same_type(self) -> None:
        """Multiple instances of the same type should all work."""
        config_yaml = """
providers:
  default: ollama-local
  instances:
    ollama-local:
      type: ollama
      base_url: http://localhost:11434
    ollama-remote:
      type: ollama
      base_url: http://remote-server:11434
"""
        with _tempfile.TemporaryDirectory() as tmp_dir:
            config_path = _os.path.join(tmp_dir, "config.yaml")
            with open(config_path, "w") as f:
                f.write(config_yaml)

            clean_env = {
                k: v
                for k, v in _os.environ.items()
                if k not in ("OLLAMA_HOST", "BRYNHILD_OLLAMA_HOST")
            }
            clean_env["BRYNHILD_CONFIG_DIR"] = tmp_dir

            with _mock.patch.dict(_os.environ, clean_env, clear=True):
                # Both instances should be creatable
                local_provider = api.create_provider(
                    provider="ollama-local",
                    model="llama3",
                    auto_profile=False,
                )
                assert local_provider.name == "ollama"
                assert "localhost" in local_provider.base_url

                remote_provider = api.create_provider(
                    provider="ollama-remote",
                    model="llama3",
                    auto_profile=False,
                )
                assert remote_provider.name == "ollama"
                assert "remote-server" in remote_provider.base_url

    def test_disabled_provider_not_used_by_default(self) -> None:
        """Disabled provider (enabled: false) config is still stored."""
        data = {
            "instances": {
                "disabled-provider": {
                    "type": "ollama",
                    "enabled": False,
                    "base_url": "http://disabled:11434",
                },
            },
        }
        config = types.ProvidersConfig.model_validate(data)
        instance = config.get_provider_config("disabled-provider")
        assert instance is not None
        assert instance.enabled is False
        # Note: Factory does not currently check enabled flag - that's the caller's responsibility

    def test_cache_ttl_zero_allowed(self) -> None:
        """cache_ttl=0 should be allowed (disables caching)."""
        data = {
            "instances": {
                "no-cache": {
                    "type": "openrouter",
                    "cache_ttl": 0,
                },
            },
        }
        config = types.ProvidersConfig.model_validate(data)
        instance = config.get_provider_config("no-cache")
        assert instance is not None
        assert instance.cache_ttl == 0

    def test_cache_ttl_negative_rejected(self) -> None:
        """cache_ttl must be non-negative."""
        data = {
            "instances": {
                "bad-cache": {
                    "type": "openrouter",
                    "cache_ttl": -1,
                },
            },
        }
        with _pytest.raises(_pydantic.ValidationError):
            types.ProvidersConfig.model_validate(data)


class TestModelBindingsWithCustomProviders:
    """Tests for model bindings referencing custom provider instances."""

    def test_model_binding_to_custom_provider_instance(self) -> None:
        """Model with binding to custom provider instance should resolve."""
        import brynhild.config as config

        # Create config with custom provider and model binding
        config_yaml = """
providers:
  default: ollama-behemoth
  instances:
    ollama-behemoth:
      type: ollama
      base_url: http://behemoth:11434

models:
  default: custom/wayfarer-70b
  registry:
    custom/wayfarer-70b:
      bindings:
        ollama-behemoth: hf.co/LatitudeGames/Wayfarer-Large-70B-Llama-3.3-GGUF:Q4_K_M
"""
        with _tempfile.TemporaryDirectory() as tmp_dir:
            config_path = _os.path.join(tmp_dir, "config.yaml")
            with open(config_path, "w") as f:
                f.write(config_yaml)

            with _mock.patch.dict(
                _os.environ,
                {"BRYNHILD_CONFIG_DIR": tmp_dir},
                clear=False,
            ):
                settings = config.Settings()

                # Model should have binding to custom provider
                identity = settings.get_model_identity("custom/wayfarer-70b")
                assert identity is not None

                # Binding should exist for the custom provider instance
                binding = identity.get_binding("ollama-behemoth")
                assert binding is not None
                assert binding.model_id == "hf.co/LatitudeGames/Wayfarer-Large-70B-Llama-3.3-GGUF:Q4_K_M"

    def test_native_model_id_for_custom_provider(self) -> None:
        """get_native_model_id should work with custom provider instances."""
        import brynhild.config as config

        config_yaml = """
providers:
  instances:
    ollama-behemoth:
      type: ollama
      base_url: http://behemoth:11434

models:
  registry:
    test/model:
      bindings:
        ollama-behemoth: custom:model:tag
        openrouter: test/model-on-openrouter
"""
        with _tempfile.TemporaryDirectory() as tmp_dir:
            config_path = _os.path.join(tmp_dir, "config.yaml")
            with open(config_path, "w") as f:
                f.write(config_yaml)

            with _mock.patch.dict(
                _os.environ,
                {"BRYNHILD_CONFIG_DIR": tmp_dir},
                clear=False,
            ):
                settings = config.Settings()

                # Should get correct native ID for each provider
                native_id = settings.get_native_model_id("test/model", "ollama-behemoth")
                assert native_id == "custom:model:tag"

                native_id_or = settings.get_native_model_id("test/model", "openrouter")
                assert native_id_or == "test/model-on-openrouter"

