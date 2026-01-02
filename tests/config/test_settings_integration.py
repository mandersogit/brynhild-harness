"""Integration tests for the complete settings system.

Tests the full integration of:
- DeepChainMapSettingsSource loading layered YAML
- Pydantic-settings merging env vars
- Settings class providing typed access
- Property aliases for backward compatibility

These tests verify end-to-end behavior of the layered config system.
"""

import os as _os
import pathlib as _pathlib
import unittest.mock as _mock

import pytest as _pytest

import brynhild.config as config
import brynhild.config.sources as sources
import brynhild.config.types as types


class TestSettingsYAMLIntegration:
    """Test Settings loading from YAML config files."""

    def test_loads_successfully(self) -> None:
        """Settings loads without error and has expected structure."""
        settings = config.Settings()

        # Verify nested config structure exists and is valid
        assert settings.behavior is not None
        assert settings.session is not None
        assert settings.models is not None
        assert settings.providers is not None

        # Verify types are correct (not specific values)
        assert isinstance(settings.behavior.max_tokens, int)
        assert isinstance(settings.session.history_limit, int)
        assert isinstance(settings.behavior.show_thinking, bool)

    def test_user_config_overrides_builtin(self, tmp_path: _pathlib.Path) -> None:
        """User config YAML overrides built-in defaults."""
        # Create user config
        user_config = tmp_path / "config.yaml"
        user_config.write_text("""
behavior:
  show_thinking: false
  show_cost: false
session:
  history_limit: 50
""")

        # Create Settings with custom user config path
        with _mock.patch.dict(_os.environ, {"BRYNHILD_CONFIG_DIR": str(tmp_path)}):
            settings = config.Settings()

        # User config values override defaults
        assert settings.behavior.show_thinking is False
        assert settings.behavior.show_cost is False
        assert settings.session.history_limit == 50

    def test_project_config_overrides_user(self, tmp_path: _pathlib.Path) -> None:
        """Project config YAML overrides user config."""
        # Create user config
        user_dir = tmp_path / "user"
        user_dir.mkdir()
        (user_dir / "config.yaml").write_text("""
behavior:
  max_tokens: 4000
  verbose: false
""")

        # Create project config
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        brynhild_dir = project_dir / ".brynhild"
        brynhild_dir.mkdir()
        (brynhild_dir / "config.yaml").write_text("""
behavior:
  max_tokens: 16000
""")

        # Patch to use our test paths
        with _mock.patch.dict(_os.environ, {"BRYNHILD_CONFIG_DIR": str(user_dir)}):
            # Create source with project root
            source = sources.DeepChainMapSettingsSource(
                config.Settings,
                project_root=project_dir,
                user_config_path=user_dir / "config.yaml",
            )
            merged = source()

        # Project overrides user for max_tokens
        assert merged["behavior"]["max_tokens"] == 16000
        # User value preserved for verbose
        assert merged["behavior"]["verbose"] is False


class TestSettingsEnvVarIntegration:
    """Test Settings loading from environment variables."""

    def test_nested_env_var_overrides_yaml(self, tmp_path: _pathlib.Path) -> None:
        """Env vars override YAML config values."""
        # Create user config
        user_config = tmp_path / "config.yaml"
        user_config.write_text("""
behavior:
  max_tokens: 4000
  verbose: false
""")

        with _mock.patch.dict(
            _os.environ,
            {
                "BRYNHILD_CONFIG_DIR": str(tmp_path),
                "BRYNHILD_BEHAVIOR__MAX_TOKENS": "32000",  # Override YAML
            },
        ):
            settings = config.Settings()

        # Env var wins over YAML
        assert settings.max_tokens == 32000
        # YAML value preserved for verbose
        assert settings.verbose is False

    def test_all_nested_env_vars_work(self) -> None:
        """Verify all nested config sections accept env vars."""
        with _mock.patch.dict(
            _os.environ,
            {
                "BRYNHILD_MODELS__DEFAULT": "test/model",
                "BRYNHILD_PROVIDERS__DEFAULT": "test-provider",
                "BRYNHILD_BEHAVIOR__VERBOSE": "true",
                "BRYNHILD_SANDBOX__ENABLED": "false",
                "BRYNHILD_LOGGING__LEVEL": "debug",
                "BRYNHILD_SESSION__AUTO_SAVE": "false",
            },
        ):
            settings = config.Settings()

        assert settings.model == "test/model"
        assert settings.provider == "test-provider"
        assert settings.verbose is True
        assert settings.sandbox.enabled is False
        assert settings.logging.level == "debug"
        assert settings.session.auto_save is False


class TestSettingsPrecedence:
    """Test complete precedence chain: constructor > env > YAML > defaults."""

    def test_constructor_overrides_env(self) -> None:
        """Constructor args override environment variables."""
        with _mock.patch.dict(
            _os.environ,
            {"BRYNHILD_BEHAVIOR__VERBOSE": "true"},
        ):
            settings = config.Settings(behavior=types.BehaviorConfig(verbose=False))

        # Constructor wins
        assert settings.verbose is False

    def test_full_precedence_chain(self, tmp_path: _pathlib.Path) -> None:
        """Test complete precedence: env > user YAML > defaults."""
        # Create user config
        user_config = tmp_path / "config.yaml"
        user_config.write_text("""
behavior:
  max_tokens: 1000
  verbose: true
  show_thinking: true
session:
  history_limit: 10
""")

        with _mock.patch.dict(
            _os.environ,
            {
                "BRYNHILD_CONFIG_DIR": str(tmp_path),
                "BRYNHILD_BEHAVIOR__MAX_TOKENS": "2000",  # Override YAML
            },
        ):
            settings = config.Settings()

        # Env (2000) > YAML (1000) > default (8192)
        assert settings.max_tokens == 2000

        # These come from YAML (no env override)
        assert settings.verbose is True
        assert settings.session.history_limit == 10

    def test_constructor_replaces_whole_section(self) -> None:
        """Constructor args replace entire nested section (not merge)."""
        # When you pass a nested model to constructor, it replaces the whole section
        settings = config.Settings(
            behavior=types.BehaviorConfig(max_tokens=3000)
            # This creates a BehaviorConfig with max_tokens=3000 and all other defaults
        )

        # Constructor value used
        assert settings.max_tokens == 3000
        # But other fields are defaults from BehaviorConfig, not from YAML
        assert settings.verbose is False  # BehaviorConfig default, not YAML


class TestBackwardCompatibility:
    """Test backward compatibility via property aliases."""

    def test_property_aliases_read_from_nested(self) -> None:
        """Property aliases correctly read from nested config."""
        settings = config.Settings(
            models=types.ModelsConfig(default="test/model"),
            providers=types.ProvidersConfig(default="test-provider"),
            behavior=types.BehaviorConfig(max_tokens=1234, verbose=True),
        )

        # Property aliases read from nested
        assert settings.model == "test/model"
        assert settings.provider == "test-provider"
        assert settings.max_tokens == 1234
        assert settings.verbose is True

    def test_property_aliases_write_to_nested(self) -> None:
        """Property aliases correctly write to nested config."""
        settings = config.Settings()

        # Write via property aliases
        settings.model = "new/model"
        settings.provider = "new-provider"
        settings.max_tokens = 9999
        settings.verbose = True

        # Nested config is updated
        assert settings.models.default == "new/model"
        assert settings.providers.default == "new-provider"
        assert settings.behavior.max_tokens == 9999
        assert settings.behavior.verbose is True

    def test_all_behavior_aliases_read(self) -> None:
        """All behavior property aliases read correctly."""
        settings = config.Settings(
            behavior=types.BehaviorConfig(
                max_tokens=5000,
                output_format="json",
                verbose=True,
                reasoning_format="thinking_tags",
            )
        )

        assert settings.max_tokens == 5000
        assert settings.output_format == "json"
        assert settings.verbose is True
        assert settings.reasoning_format == "thinking_tags"

    def test_all_behavior_aliases_write(self) -> None:
        """All behavior property aliases write correctly."""
        settings = config.Settings()

        settings.output_format = "json"
        settings.reasoning_format = "thinking_tags"

        assert settings.behavior.output_format == "json"
        assert settings.behavior.reasoning_format == "thinking_tags"

    def test_sandbox_aliases_read_and_write(self) -> None:
        """Sandbox property aliases work correctly."""
        settings = config.Settings(
            sandbox=types.SandboxConfig(
                enabled=False,
                allow_network=True,
                allowed_paths=["/tmp", "/var/data"],
            )
        )

        # Read via aliases
        assert settings.sandbox_enabled is False
        assert settings.sandbox_allow_network is True
        assert settings.allowed_paths == "/tmp,/var/data"

        # Write via aliases
        settings.sandbox_enabled = True
        settings.sandbox_allow_network = False
        settings.allowed_paths = "/new/path,/other/path"

        # Verify nested config updated
        assert settings.sandbox.enabled is True
        assert settings.sandbox.allow_network is False
        assert settings.sandbox.allowed_paths == ["/new/path", "/other/path"]

    def test_allowed_paths_empty_string_handling(self) -> None:
        """allowed_paths handles empty strings correctly."""
        settings = config.Settings()

        # Default should be empty
        assert settings.allowed_paths == ""

        # Setting empty string should result in empty list
        settings.allowed_paths = ""
        assert settings.sandbox.allowed_paths == []

        # Setting whitespace-only should result in empty list
        settings.allowed_paths = "  "
        assert settings.sandbox.allowed_paths == []

    def test_logging_aliases_read_and_write(self) -> None:
        """Logging property aliases work correctly."""
        settings = config.Settings(
            logging=types.LoggingConfig(
                enabled=False,
                dir="/custom/logs",
                private=False,
                raw_payloads=True,
            )
        )

        # Read via aliases
        assert settings.log_conversations is False
        assert settings.log_dir == "/custom/logs"
        assert settings.log_dir_private is False
        assert settings.raw_log is True

        # Write via aliases
        settings.log_conversations = True
        settings.log_dir = "/new/logs"
        settings.log_dir_private = True
        settings.raw_log = False

        # Verify nested config updated
        assert settings.logging.enabled is True
        assert settings.logging.dir == "/new/logs"
        assert settings.logging.private is True
        assert settings.logging.raw_payloads is False

    def test_log_dir_empty_handling(self) -> None:
        """log_dir handles empty/None correctly."""
        settings = config.Settings()

        # Default (None in nested) returns empty string via alias
        assert settings.log_dir == ""

        # Setting empty string stores None
        settings.log_dir = ""
        assert settings.logging.dir is None

    def test_tools_disabled_aliases(self) -> None:
        """Tools disabled property aliases work correctly."""
        settings = config.Settings(
            tools=types.ToolsConfig(disabled={"Bash": True, "Write": True, "Read": False})
        )

        # disabled_tools returns comma-separated string of disabled tools
        disabled = settings.disabled_tools
        assert "Bash" in disabled
        assert "Write" in disabled
        assert "Read" not in disabled  # False means not disabled

    def test_disable_builtin_tools_marker(self) -> None:
        """disable_builtin_tools checks for __builtin__ marker."""
        # Without marker
        settings = config.Settings()
        assert settings.disable_builtin_tools is False

        # With marker
        settings = config.Settings(tools=types.ToolsConfig(disabled={"__builtin__": True}))
        assert settings.disable_builtin_tools is True


class TestMigrationDetection:
    """Test detection of legacy environment variables.

    Note: conftest.py sets BRYNHILD_SKIP_MIGRATION_CHECK=1 to allow tests to run
    even if user's .env has legacy vars. These tests explicitly unset it.
    """

    def _env_without_skip(self, extra: dict[str, str]) -> dict[str, str]:
        """Create env dict without the skip flag and with legacy vars."""
        env = {k: v for k, v in _os.environ.items() if k != "BRYNHILD_SKIP_MIGRATION_CHECK"}
        env.update(extra)
        return env

    def test_detects_legacy_model_env_var(self) -> None:
        """BRYNHILD_MODEL triggers migration error."""
        env = self._env_without_skip({"BRYNHILD_MODEL": "some-model"})
        with (
            _mock.patch.dict(_os.environ, env, clear=True),
            _pytest.raises(ValueError, match="Legacy environment variables"),
        ):
            config.Settings()

    def test_detects_legacy_provider_env_var(self) -> None:
        """BRYNHILD_PROVIDER triggers migration error."""
        env = self._env_without_skip({"BRYNHILD_PROVIDER": "ollama"})
        with (
            _mock.patch.dict(_os.environ, env, clear=True),
            _pytest.raises(ValueError, match="Legacy environment variables"),
        ):
            config.Settings()

    def test_detects_legacy_verbose_env_var(self) -> None:
        """BRYNHILD_VERBOSE triggers migration error."""
        env = self._env_without_skip({"BRYNHILD_VERBOSE": "true"})
        with (
            _mock.patch.dict(_os.environ, env, clear=True),
            _pytest.raises(ValueError, match="Legacy environment variables"),
        ):
            config.Settings()

    def test_migration_error_includes_new_syntax(self) -> None:
        """Migration error message includes the new env var syntax."""
        env = self._env_without_skip({"BRYNHILD_MODEL": "some-model"})
        with (
            _mock.patch.dict(_os.environ, env, clear=True),
            _pytest.raises(ValueError) as exc_info,
        ):
            config.Settings()

        error_msg = str(exc_info.value)
        assert "BRYNHILD_MODEL" in error_msg
        assert "BRYNHILD_MODELS__DEFAULT" in error_msg

    def test_no_error_with_new_env_var_syntax(self) -> None:
        """New nested env var syntax does not trigger migration error."""
        # Start with clean env, no legacy vars, no skip flag
        clean_env = {
            k: v
            for k, v in _os.environ.items()
            if k
            not in [
                "BRYNHILD_MODEL",
                "BRYNHILD_PROVIDER",
                "BRYNHILD_VERBOSE",
                "BRYNHILD_MAX_TOKENS",
                "BRYNHILD_OUTPUT_FORMAT",
                "BRYNHILD_SANDBOX_ENABLED",
                "BRYNHILD_SANDBOX_ALLOW_NETWORK",
                "BRYNHILD_LOG_CONVERSATIONS",
                "BRYNHILD_LOG_DIR",
                "BRYNHILD_LOG_DIR_PRIVATE",
                "BRYNHILD_RAW_LOG",
                "BRYNHILD_DISABLED_TOOLS",
                "BRYNHILD_DISABLE_BUILTIN_TOOLS",
                "BRYNHILD_SKIP_MIGRATION_CHECK",
            ]
        }
        clean_env["BRYNHILD_MODELS__DEFAULT"] = "some-model"

        with _mock.patch.dict(_os.environ, clean_env, clear=True):
            # Should not raise
            settings = config.Settings()
            assert settings.model == "some-model"

    def test_skip_check_env_var_bypasses_detection(self) -> None:
        """BRYNHILD_SKIP_MIGRATION_CHECK=1 bypasses migration detection."""
        env = {
            "BRYNHILD_SKIP_MIGRATION_CHECK": "1",
            "BRYNHILD_MODEL": "legacy-model",  # Would normally trigger error
        }
        with _mock.patch.dict(_os.environ, env, clear=False):
            # Should NOT raise because skip is set
            settings = config.Settings()
            # Note: legacy var is ignored, model comes from defaults
            assert settings.model is not None


class TestIntrospection:
    """Test config introspection for strict validation mode."""

    def test_collects_extra_fields_from_yaml(self, tmp_path: _pathlib.Path) -> None:
        """Extra fields in YAML are captured for auditing."""
        # Create user config with typos
        user_config = tmp_path / "config.yaml"
        user_config.write_text("""
behavior:
  verboes: true  # typo
  max_tokns: 1000  # typo
""")

        with _mock.patch.dict(_os.environ, {"BRYNHILD_CONFIG_DIR": str(tmp_path)}):
            settings = config.Settings()

        # Extra fields are captured
        extras = settings.collect_all_extra_fields()
        assert "behavior.verboes" in extras
        assert "behavior.max_tokns" in extras

    def test_has_extra_fields_detects_typos(self, tmp_path: _pathlib.Path) -> None:
        """has_extra_fields() returns True when config has typos."""
        # Create user config with typo
        user_config = tmp_path / "config.yaml"
        user_config.write_text("""
behavir:  # typo at section level
  verbose: true
""")

        with _mock.patch.dict(_os.environ, {"BRYNHILD_CONFIG_DIR": str(tmp_path)}):
            settings = config.Settings()

        assert settings.has_extra_fields() is True
