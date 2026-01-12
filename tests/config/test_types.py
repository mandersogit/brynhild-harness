"""Tests for configuration type definitions.

Tests for the Pydantic models in brynhild.config.types.
"""

import pydantic as _pydantic
import pytest as _pytest

import brynhild.config.types as types

# =============================================================================
# ConfigBase Introspection Tests
# =============================================================================


class TestConfigBaseIntrospection:
    """Tests for ConfigBase introspection methods (extra field auditing)."""

    def test_get_extra_fields_empty(self) -> None:
        """Should return empty dict when no extra fields."""
        config = types.BehaviorConfig()
        assert config.get_extra_fields() == {}
        assert not config.has_extra_fields()

    def test_get_extra_fields_with_extras(self) -> None:
        """Should return dict of extra fields when present."""
        config = types.BehaviorConfig.model_validate(
            {
                "max_tokens": 4096,
                "typo_field": "value1",
                "another_unknown": 42,
            }
        )
        extras = config.get_extra_fields()
        assert extras == {"typo_field": "value1", "another_unknown": 42}
        assert config.has_extra_fields()

    def test_collect_all_extra_fields_flat(self) -> None:
        """Should collect extra fields with dotted paths."""
        config = types.BehaviorConfig.model_validate(
            {
                "verboes": True,  # typo
                "max_tokens": 4096,
            }
        )
        all_extras = config.collect_all_extra_fields()
        assert all_extras == {"verboes": True}

    def test_collect_all_extra_fields_with_prefix(self) -> None:
        """Should use prefix for dotted paths."""
        config = types.BehaviorConfig.model_validate(
            {
                "typo": "value",
            }
        )
        all_extras = config.collect_all_extra_fields(prefix="behavior")
        assert all_extras == {"behavior.typo": "value"}

    def test_collect_all_extra_fields_empty(self) -> None:
        """Should return empty dict when no extra fields anywhere."""
        config = types.BehaviorConfig()
        assert config.collect_all_extra_fields() == {}

    def test_collect_all_extra_fields_nested(self) -> None:
        """Should collect extra fields from nested ConfigBase objects."""
        # Create a nested config structure for testing recursion
        # We'll use a synthetic parent with a nested ConfigBase field

        import pydantic as _pydantic

        class NestedTestConfig(types.ConfigBase):
            """Test config with nested ConfigBase field."""

            behavior: types.BehaviorConfig = _pydantic.Field(default_factory=types.BehaviorConfig)
            sandbox: types.SandboxConfig = _pydantic.Field(default_factory=types.SandboxConfig)

        # Create with extra fields at multiple levels
        config = NestedTestConfig.model_validate(
            {
                "top_level_typo": "should appear",
                "behavior": {
                    "max_tokens": 4096,
                    "verboes": True,  # typo in nested config
                },
                "sandbox": {
                    "enabled": True,
                    "unknwon_sandbox_field": 123,  # typo in different nested config
                },
            }
        )

        all_extras = config.collect_all_extra_fields()

        # Should have extras from all levels with correct dotted paths
        assert "top_level_typo" in all_extras
        assert all_extras["top_level_typo"] == "should appear"
        assert "behavior.verboes" in all_extras
        assert all_extras["behavior.verboes"] is True
        assert "sandbox.unknwon_sandbox_field" in all_extras
        assert all_extras["sandbox.unknwon_sandbox_field"] == 123
        assert len(all_extras) == 3

    def test_collect_all_extra_fields_deeply_nested(self) -> None:
        """Should collect extra fields from deeply nested structures."""
        import pydantic as _pydantic

        class Level2(types.ConfigBase):
            name: str = "default"

        class Level1(types.ConfigBase):
            level2: Level2 = _pydantic.Field(default_factory=Level2)

        class Root(types.ConfigBase):
            level1: Level1 = _pydantic.Field(default_factory=Level1)

        config = Root.model_validate(
            {
                "root_extra": "r",
                "level1": {
                    "level1_extra": "l1",
                    "level2": {
                        "name": "custom",
                        "level2_extra": "l2",
                    },
                },
            }
        )

        all_extras = config.collect_all_extra_fields()

        assert all_extras == {
            "root_extra": "r",
            "level1.level1_extra": "l1",
            "level1.level2.level2_extra": "l2",
        }


# =============================================================================
# BehaviorConfig Tests
# =============================================================================


class TestBehaviorConfig:
    """Tests for BehaviorConfig."""

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        config = types.BehaviorConfig()
        assert config.max_tokens == 8192
        assert config.output_format == "text"
        assert config.verbose is False
        assert config.show_thinking is False
        assert config.show_cost is False
        assert config.reasoning_format == "auto"
        assert config.reasoning_level == "auto"

    def test_max_tokens_validation_minimum(self) -> None:
        """max_tokens must be at least 1."""
        with _pytest.raises(_pydantic.ValidationError) as exc_info:
            types.BehaviorConfig(max_tokens=0)
        assert "max_tokens" in str(exc_info.value)

    def test_max_tokens_validation_maximum(self) -> None:
        """max_tokens must be at most 200000."""
        with _pytest.raises(_pydantic.ValidationError) as exc_info:
            types.BehaviorConfig(max_tokens=200001)
        assert "max_tokens" in str(exc_info.value)

    def test_max_tokens_valid_range(self) -> None:
        """max_tokens should accept valid values."""
        config = types.BehaviorConfig(max_tokens=1)
        assert config.max_tokens == 1
        config = types.BehaviorConfig(max_tokens=200000)
        assert config.max_tokens == 200000

    def test_output_format_validation(self) -> None:
        """output_format must be one of the allowed values."""
        with _pytest.raises(_pydantic.ValidationError):
            types.BehaviorConfig(output_format="invalid")  # type: ignore

    def test_output_format_valid_values(self) -> None:
        """output_format should accept all valid values."""
        for fmt in ("text", "json", "stream"):
            config = types.BehaviorConfig(output_format=fmt)  # type: ignore
            assert config.output_format == fmt

    def test_reasoning_format_validation(self) -> None:
        """reasoning_format must be one of the allowed values."""
        with _pytest.raises(_pydantic.ValidationError):
            types.BehaviorConfig(reasoning_format="invalid")  # type: ignore

    def test_reasoning_level_accepts_standard_values(self) -> None:
        """reasoning_level should accept all standard values."""
        standard_levels = ("auto", "off", "minimal", "low", "medium", "high", "maximum")
        for level in standard_levels:
            config = types.BehaviorConfig(reasoning_level=level)
            assert config.reasoning_level == level

    def test_reasoning_level_accepts_custom_values(self) -> None:
        """reasoning_level should accept custom values (string type)."""
        # Custom values are allowed - warning happens at runtime, not validation
        config = types.BehaviorConfig(reasoning_level="custom-value")
        assert config.reasoning_level == "custom-value"

    def test_reasoning_level_accepts_raw_prefix(self) -> None:
        """reasoning_level should accept raw: prefixed values."""
        config = types.BehaviorConfig(reasoning_level="raw:thinking_budget=65536")
        assert config.reasoning_level == "raw:thinking_budget=65536"

    def test_from_dict(self) -> None:
        """Should load from dict (as would come from YAML)."""
        data = {
            "max_tokens": 4096,
            "verbose": True,
            "show_thinking": True,
        }
        config = types.BehaviorConfig.model_validate(data)
        assert config.max_tokens == 4096
        assert config.verbose is True
        assert config.show_thinking is True
        # Unset fields use defaults
        assert config.output_format == "text"

    def test_extra_fields_preserved(self) -> None:
        """Extra fields should be preserved for introspection (not raise errors)."""
        data = {
            "max_tokens": 4096,
            "unknown_field": "should be preserved",
        }
        config = types.BehaviorConfig.model_validate(data)
        assert config.max_tokens == 4096
        # Extra fields are preserved, accessible via model_extra
        assert config.has_extra_fields()
        assert config.get_extra_fields() == {"unknown_field": "should be preserved"}


# =============================================================================
# SandboxConfig Tests
# =============================================================================


class TestSandboxConfig:
    """Tests for SandboxConfig."""

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        config = types.SandboxConfig()
        assert config.enabled is True
        assert config.allow_network is False
        assert config.allowed_paths == []

    def test_allowed_paths_list(self) -> None:
        """allowed_paths should accept a list of strings."""
        config = types.SandboxConfig(allowed_paths=["/tmp", "/var/data"])
        assert config.allowed_paths == ["/tmp", "/var/data"]

    def test_from_dict(self) -> None:
        """Should load from dict."""
        data = {
            "enabled": False,
            "allow_network": True,
            "allowed_paths": ["/custom/path"],
        }
        config = types.SandboxConfig.model_validate(data)
        assert config.enabled is False
        assert config.allow_network is True
        assert config.allowed_paths == ["/custom/path"]


class TestSandboxConfigPathParsing:
    """Tests for allowed_paths colon-delimited parsing (Unix convention)."""

    def test_colon_delimited_string(self) -> None:
        """Should parse colon-delimited string like Unix PATH."""
        config = types.SandboxConfig.model_validate(
            {
                "allowed_paths": "/Users/me/git:/tmp:/var/data",
            }
        )
        assert config.allowed_paths == ["/Users/me/git", "/tmp", "/var/data"]

    def test_single_path_string(self) -> None:
        """Should accept a single path as string."""
        config = types.SandboxConfig.model_validate(
            {
                "allowed_paths": "/Users/me/git",
            }
        )
        assert config.allowed_paths == ["/Users/me/git"]

    def test_json_array_string(self) -> None:
        """Should accept JSON array for backwards compatibility."""
        config = types.SandboxConfig.model_validate(
            {
                "allowed_paths": '["/Users/me/git", "/tmp"]',
            }
        )
        assert config.allowed_paths == ["/Users/me/git", "/tmp"]

    def test_list_passthrough(self) -> None:
        """Should pass through lists unchanged."""
        config = types.SandboxConfig.model_validate(
            {
                "allowed_paths": ["/path1", "/path2"],
            }
        )
        assert config.allowed_paths == ["/path1", "/path2"]

    def test_empty_string(self) -> None:
        """Should handle empty string as empty list."""
        config = types.SandboxConfig.model_validate(
            {
                "allowed_paths": "",
            }
        )
        assert config.allowed_paths == []

    def test_whitespace_string(self) -> None:
        """Should handle whitespace-only string as empty list."""
        config = types.SandboxConfig.model_validate(
            {
                "allowed_paths": "   ",
            }
        )
        assert config.allowed_paths == []

    def test_json_empty_array(self) -> None:
        """Should handle JSON empty array."""
        config = types.SandboxConfig.model_validate(
            {
                "allowed_paths": "[]",
            }
        )
        assert config.allowed_paths == []

    def test_colon_delimited_with_whitespace(self) -> None:
        """Whitespace around colons is NOT trimmed (paths can have spaces)."""
        # Note: we don't trim because paths might legitimately have spaces
        config = types.SandboxConfig.model_validate(
            {
                "allowed_paths": "/path one:/path two",
            }
        )
        assert config.allowed_paths == ["/path one", "/path two"]

    def test_malformed_json_falls_through_to_colon(self) -> None:
        """Malformed JSON starting with [ falls through to colon parsing."""
        config = types.SandboxConfig.model_validate(
            {
                "allowed_paths": "[not valid json",
            }
        )
        # Falls through to colon parsing, no colon so single path
        assert config.allowed_paths == ["[not valid json"]

    def test_direct_construction_with_list(self) -> None:
        """Direct construction with list should work."""
        config = types.SandboxConfig(allowed_paths=["/a", "/b"])
        assert config.allowed_paths == ["/a", "/b"]

    def test_direct_construction_with_string(self) -> None:
        """Direct construction with colon-delimited string should work."""
        config = types.SandboxConfig(allowed_paths="/a:/b")  # type: ignore[arg-type]
        assert config.allowed_paths == ["/a", "/b"]


class TestSandboxConfigEnvVarParsing:
    """Tests for allowed_paths parsing from environment variables.

    These tests verify that the model_validator correctly handles colon-delimited
    strings from env vars before pydantic-settings tries to JSON-parse them.
    """

    def test_colon_delimited_from_env_var(
        self, monkeypatch: _pytest.MonkeyPatch
    ) -> None:
        """Colon-delimited should work when set as environment variable."""
        monkeypatch.setenv("BRYNHILD_SANDBOX__ALLOWED_PATHS", "/path/one:/path/two")

        # Must test via Settings since that's where pydantic-settings processing happens
        import brynhild.config.settings as settings

        # Clear any cached settings
        s = settings.Settings.construct_without_dotenv()
        assert s.sandbox.allowed_paths == ["/path/one", "/path/two"]

    def test_single_path_from_env_var(self, monkeypatch: _pytest.MonkeyPatch) -> None:
        """Single path should work when set as environment variable."""
        monkeypatch.setenv("BRYNHILD_SANDBOX__ALLOWED_PATHS", "/single/path")

        import brynhild.config.settings as settings

        s = settings.Settings.construct_without_dotenv()
        assert s.sandbox.allowed_paths == ["/single/path"]

    def test_json_array_from_env_var(self, monkeypatch: _pytest.MonkeyPatch) -> None:
        """JSON array should still work when set as environment variable."""
        monkeypatch.setenv(
            "BRYNHILD_SANDBOX__ALLOWED_PATHS", '["/path/one", "/path/two"]'
        )

        import brynhild.config.settings as settings

        s = settings.Settings.construct_without_dotenv()
        assert s.sandbox.allowed_paths == ["/path/one", "/path/two"]

    def test_empty_string_from_env_var(self, monkeypatch: _pytest.MonkeyPatch) -> None:
        """Empty string should result in empty list."""
        monkeypatch.setenv("BRYNHILD_SANDBOX__ALLOWED_PATHS", "")

        import brynhild.config.settings as settings

        s = settings.Settings.construct_without_dotenv()
        assert s.sandbox.allowed_paths == []


# =============================================================================
# LoggingConfig Tests
# =============================================================================


class TestLoggingConfig:
    """Tests for LoggingConfig."""

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        config = types.LoggingConfig()
        assert config.enabled is True
        assert config.dir is None
        assert config.level == "info"
        assert config.private is True
        assert config.raw_payloads is False

    def test_level_validation(self) -> None:
        """level must be one of the allowed values."""
        with _pytest.raises(_pydantic.ValidationError):
            types.LoggingConfig(level="invalid")  # type: ignore

    def test_level_valid_values(self) -> None:
        """level should accept all valid values."""
        for level in ("debug", "info", "warning", "error"):
            config = types.LoggingConfig(level=level)  # type: ignore
            assert config.level == level

    def test_custom_dir(self) -> None:
        """dir should accept a custom path."""
        config = types.LoggingConfig(dir="/var/log/brynhild")
        assert config.dir == "/var/log/brynhild"


# =============================================================================
# SessionConfig Tests
# =============================================================================


class TestSessionConfig:
    """Tests for SessionConfig."""

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        config = types.SessionConfig()
        assert config.auto_save is True
        assert config.history_limit == 100

    def test_history_limit_validation(self) -> None:
        """history_limit must be at least 1."""
        with _pytest.raises(_pydantic.ValidationError):
            types.SessionConfig(history_limit=0)

    def test_history_limit_valid(self) -> None:
        """history_limit should accept valid values."""
        config = types.SessionConfig(history_limit=1)
        assert config.history_limit == 1
        config = types.SessionConfig(history_limit=1000)
        assert config.history_limit == 1000


# =============================================================================
# ProviderInstanceConfig Tests
# =============================================================================


class TestProviderInstanceConfig:
    """Tests for ProviderInstanceConfig."""

    def test_type_required(self) -> None:
        """type field is required."""
        with _pytest.raises(_pydantic.ValidationError) as exc_info:
            types.ProviderInstanceConfig()
        assert "type" in str(exc_info.value)

    def test_default_values(self) -> None:
        """Should have sensible defaults for optional fields."""
        config = types.ProviderInstanceConfig(type="ollama")
        assert config.type == "ollama"
        assert config.enabled is True
        assert config.base_url is None
        assert config.cache_ttl == 3600

    def test_cache_ttl_validation(self) -> None:
        """cache_ttl must be non-negative."""
        with _pytest.raises(_pydantic.ValidationError):
            types.ProviderInstanceConfig(type="ollama", cache_ttl=-1)

    def test_cache_ttl_zero_allowed(self) -> None:
        """cache_ttl=0 should be allowed (disable caching)."""
        config = types.ProviderInstanceConfig(type="ollama", cache_ttl=0)
        assert config.cache_ttl == 0

    def test_custom_base_url(self) -> None:
        """base_url should accept a custom URL."""
        config = types.ProviderInstanceConfig(type="ollama", base_url="http://localhost:11434")
        assert config.base_url == "http://localhost:11434"

    def test_extra_fields_allowed(self) -> None:
        """Extra provider-specific fields should be allowed."""
        data = {
            "type": "openrouter",
            "enabled": True,
            "api_version": "2024-01",
            "custom_setting": "value",
        }
        config = types.ProviderInstanceConfig.model_validate(data)
        assert config.enabled is True
        # Extra fields are stored
        assert config.api_version == "2024-01"  # type: ignore
        assert config.custom_setting == "value"  # type: ignore


# =============================================================================
# ProvidersConfig Tests
# =============================================================================


class TestProvidersConfig:
    """Tests for ProvidersConfig."""

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        config = types.ProvidersConfig()
        assert config.default == "openrouter"

    def test_get_provider_config_missing(self) -> None:
        """get_provider_config should return None for unknown provider."""
        config = types.ProvidersConfig()
        provider_config = config.get_provider_config("unknown")
        assert provider_config is None

    def test_get_provider_config_from_dict(self) -> None:
        """get_provider_config should parse nested dicts with type field."""
        data = {
            "default": "ollama",
            "instances": {
                "ollama": {
                    "type": "ollama",
                    "enabled": True,
                    "base_url": "http://localhost:11434",
                    "cache_ttl": 1800,
                },
            },
        }
        config = types.ProvidersConfig.model_validate(data)
        assert config.default == "ollama"

        provider_config = config.get_provider_config("ollama")
        assert provider_config is not None
        assert provider_config.type == "ollama"
        assert provider_config.enabled is True
        assert provider_config.base_url == "http://localhost:11434"

    def test_legacy_config_format_detected(self) -> None:
        """Legacy config without type field should raise helpful error."""
        data = {
            "default": "ollama",
            "ollama": {  # Legacy: no instances wrapper, no type
                "enabled": True,
                "base_url": "http://localhost:11434",
            },
        }
        with _pytest.raises(ValueError) as exc_info:
            types.ProvidersConfig.model_validate(data)
        assert "Legacy provider config detected" in str(exc_info.value)
        assert "type" in str(exc_info.value)


# =============================================================================
# PluginConfig Tests
# =============================================================================


class TestPluginConfig:
    """Tests for PluginConfig."""

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        config = types.PluginConfig()
        assert config.enabled is True
        assert config.timeout == 300

    def test_timeout_validation(self) -> None:
        """timeout must be at least 1."""
        with _pytest.raises(_pydantic.ValidationError):
            types.PluginConfig(timeout=0)

    def test_extra_fields_allowed(self) -> None:
        """Extra plugin-specific fields should be allowed."""
        data = {
            "enabled": True,
            "custom_option": "value",
        }
        config = types.PluginConfig.model_validate(data)
        assert config.custom_option == "value"  # type: ignore


# =============================================================================
# PluginsConfig Tests
# =============================================================================


class TestPluginsConfig:
    """Tests for PluginsConfig."""

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        config = types.PluginsConfig()
        assert config.search_paths == []
        assert config.enabled == {}

    def test_get_plugin_config_missing(self) -> None:
        """get_plugin_config should return defaults for unknown plugin."""
        config = types.PluginsConfig()
        plugin_config = config.get_plugin_config("unknown")
        assert plugin_config.enabled is True
        assert plugin_config.timeout == 300

    def test_is_plugin_enabled_default(self) -> None:
        """is_plugin_enabled should return True by default."""
        config = types.PluginsConfig()
        assert config.is_plugin_enabled("unknown") is True

    def test_is_plugin_enabled_explicit_disable(self) -> None:
        """is_plugin_enabled should respect enabled dict."""
        config = types.PluginsConfig(enabled={"my-plugin": False})
        assert config.is_plugin_enabled("my-plugin") is False
        assert config.is_plugin_enabled("other-plugin") is True

    def test_is_plugin_enabled_from_plugin_config(self) -> None:
        """is_plugin_enabled should check plugin-specific config."""
        data = {
            "my-plugin": {
                "enabled": False,
                "timeout": 600,
            },
        }
        config = types.PluginsConfig.model_validate(data)
        assert config.is_plugin_enabled("my-plugin") is False


# =============================================================================
# ToolConfig Tests
# =============================================================================


class TestToolConfig:
    """Tests for ToolConfig."""

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        config = types.ToolConfig()
        assert config.require_approval == "once"
        assert config.allowed_commands == []
        assert config.blocked_commands == []
        assert config.allowed_paths == []

    def test_require_approval_validation(self) -> None:
        """require_approval must be one of the allowed values."""
        with _pytest.raises(_pydantic.ValidationError):
            types.ToolConfig(require_approval="invalid")  # type: ignore

    def test_require_approval_valid_values(self) -> None:
        """require_approval should accept all valid values."""
        for approval in ("always", "once", "never"):
            config = types.ToolConfig(require_approval=approval)  # type: ignore
            assert config.require_approval == approval

    def test_command_lists(self) -> None:
        """Should accept command whitelist/blacklist."""
        config = types.ToolConfig(
            allowed_commands=["git *", "npm *"],
            blocked_commands=["rm -rf *"],
        )
        assert config.allowed_commands == ["git *", "npm *"]
        assert config.blocked_commands == ["rm -rf *"]


# =============================================================================
# ToolsConfig Tests
# =============================================================================


class TestToolsConfig:
    """Tests for ToolsConfig."""

    def test_default_values(self) -> None:
        """Should have sensible defaults."""
        config = types.ToolsConfig()
        assert config.disabled == {}

    def test_get_tool_config_missing(self) -> None:
        """get_tool_config should return defaults for unknown tool."""
        config = types.ToolsConfig()
        tool_config = config.get_tool_config("unknown")
        assert tool_config.require_approval == "once"

    def test_is_tool_disabled_default(self) -> None:
        """is_tool_disabled should return False by default."""
        config = types.ToolsConfig()
        assert config.is_tool_disabled("unknown") is False

    def test_is_tool_disabled_explicit(self) -> None:
        """is_tool_disabled should respect disabled dict."""
        config = types.ToolsConfig(disabled={"dangerous-tool": True})
        assert config.is_tool_disabled("dangerous-tool") is True
        assert config.is_tool_disabled("safe-tool") is False

    def test_get_tool_config_from_dict(self) -> None:
        """get_tool_config should parse nested dicts."""
        data = {
            "bash": {
                "require_approval": "always",
                "blocked_commands": ["rm -rf /"],
            },
        }
        config = types.ToolsConfig.model_validate(data)

        tool_config = config.get_tool_config("bash")
        assert tool_config.require_approval == "always"
        assert tool_config.blocked_commands == ["rm -rf /"]


# =============================================================================
# Dynamic Container Introspection Tests
# =============================================================================


class TestDynamicContainerIntrospection:
    """Tests for introspection into dynamic config containers.

    The typed `instances` pattern should enable collect_all_extra_fields()
    to recurse into provider/plugin/tool configs and detect typos.
    """

    def test_providers_instances_validated_at_load(self) -> None:
        """Provider instances should be validated as ProviderInstanceConfig."""
        data = {
            "default": "openrouter",
            "instances": {
                "openrouter": {
                    "type": "openrouter",
                    "enabled": True,
                    "cache_ttl": 7200,
                },
                "ollama": {
                    "type": "ollama",
                    "base_url": "http://localhost:11434",
                },
            },
        }
        config = types.ProvidersConfig.model_validate(data)

        # Instances should be typed, not raw dicts
        assert isinstance(config.instances.get("openrouter"), types.ProviderInstanceConfig)
        assert isinstance(config.instances.get("ollama"), types.ProviderInstanceConfig)
        assert config.instances["openrouter"].type == "openrouter"
        assert config.instances["openrouter"].cache_ttl == 7200
        assert config.instances["ollama"].type == "ollama"
        assert config.instances["ollama"].base_url == "http://localhost:11434"

    def test_providers_typo_detected_via_introspection(self) -> None:
        """Typos inside provider instances should be detected."""
        data = {
            "instances": {
                "openrouter": {
                    "type": "openrouter",
                    "enabled": True,
                    "enabeld": True,  # TYPO
                    "cache_ttl": 3600,
                },
            },
        }
        config = types.ProvidersConfig.model_validate(data)

        # The typo should be in the instance's extra fields
        provider = config.instances["openrouter"]
        assert provider.has_extra_fields()
        assert "enabeld" in provider.get_extra_fields()

        # And should be found by collect_all_extra_fields
        all_extras = config.collect_all_extra_fields()
        assert "instances.openrouter.enabeld" in all_extras

    def test_plugins_instances_validated_at_load(self) -> None:
        """Plugin instances should be validated as PluginConfig."""
        data = {
            "search_paths": ["/custom/plugins"],
            "my-plugin": {
                "enabled": True,
                "timeout": 600,
            },
        }
        config = types.PluginsConfig.model_validate(data)

        assert isinstance(config.instances.get("my-plugin"), types.PluginConfig)
        assert config.instances["my-plugin"].timeout == 600

    def test_plugins_typo_detected_via_introspection(self) -> None:
        """Typos inside plugin instances should be detected."""
        data = {
            "my-plugin": {
                "enabled": True,
                "timout": 600,  # TYPO
            },
        }
        config = types.PluginsConfig.model_validate(data)

        plugin = config.instances["my-plugin"]
        assert plugin.has_extra_fields()
        assert "timout" in plugin.get_extra_fields()

        all_extras = config.collect_all_extra_fields()
        assert "instances.my-plugin.timout" in all_extras

    def test_tools_instances_validated_at_load(self) -> None:
        """Tool instances should be validated as ToolConfig."""
        data = {
            "bash": {
                "require_approval": "always",
                "blocked_commands": ["rm -rf /"],
            },
        }
        config = types.ToolsConfig.model_validate(data)

        assert isinstance(config.instances.get("bash"), types.ToolConfig)
        assert config.instances["bash"].require_approval == "always"

    def test_tools_typo_detected_via_introspection(self) -> None:
        """Typos inside tool instances should be detected."""
        data = {
            "bash": {
                "require_approval": "always",
                "blocked_comands": ["rm -rf /"],  # TYPO
            },
        }
        config = types.ToolsConfig.model_validate(data)

        tool = config.instances["bash"]
        assert tool.has_extra_fields()
        assert "blocked_comands" in tool.get_extra_fields()

        all_extras = config.collect_all_extra_fields()
        assert "instances.bash.blocked_comands" in all_extras

    def test_multiple_instances_with_multiple_typos(self) -> None:
        """Multiple typos across multiple instances should all be found."""
        data = {
            "instances": {
                "openrouter": {
                    "type": "openrouter",
                    "typo1": "value1",
                },
                "ollama": {
                    "type": "ollama",
                    "typo2": "value2",
                    "typo3": "value3",
                },
            },
        }
        config = types.ProvidersConfig.model_validate(data)

        all_extras = config.collect_all_extra_fields()
        assert "instances.openrouter.typo1" in all_extras
        assert "instances.ollama.typo2" in all_extras
        assert "instances.ollama.typo3" in all_extras

    def test_valid_config_no_extra_fields(self) -> None:
        """Valid config with no typos should have no extra fields."""
        data = {
            "default": "openrouter",
            "instances": {
                "openrouter": {
                    "type": "openrouter",
                    "enabled": True,
                    "cache_ttl": 3600,
                },
            },
        }
        config = types.ProvidersConfig.model_validate(data)

        # No extra fields on the provider instance
        provider = config.instances["openrouter"]
        assert not provider.has_extra_fields()

        # No extra fields anywhere
        all_extras = config.collect_all_extra_fields()
        assert len(all_extras) == 0
