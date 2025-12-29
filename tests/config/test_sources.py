"""Tests for custom pydantic-settings sources.

Tests for DeepChainMapSettingsSource:
- Loading from single file
- Loading from multiple files (merge order)
- Handling missing files gracefully
- Handling malformed YAML
- Integration with pydantic-settings
"""

import pathlib as _pathlib
import typing as _typing

import pydantic as _pydantic
import pydantic_settings as _pydantic_settings
import pytest as _pytest
import yaml as _yaml

import brynhild.config.sources as sources


class TestDeepChainMapSettingsSourceClass:
    """Verify the DeepChainMapSettingsSource class API."""

    def test_is_pydantic_settings_source(self) -> None:
        """DeepChainMapSettingsSource should be a pydantic-settings source."""
        assert issubclass(
            sources.DeepChainMapSettingsSource,
            _pydantic_settings.PydanticBaseSettingsSource,
        )


class TestHelperFunctions:
    """Tests for path helper functions."""

    def test_get_builtin_defaults_path(self) -> None:
        """Should return path to defaults/config.yaml."""
        path = sources.get_builtin_defaults_path()
        assert path.name == "config.yaml"
        assert path.parent.name == "defaults"

    def test_get_user_config_path_default(
        self,
        monkeypatch: _pytest.MonkeyPatch,
    ) -> None:
        """Without env var, should return XDG-compliant user config path."""
        monkeypatch.delenv("BRYNHILD_CONFIG_DIR", raising=False)
        path = sources.get_user_config_path()
        assert path == _pathlib.Path.home() / ".config" / "brynhild" / "config.yaml"

    def test_get_user_config_path_with_env_var(
        self,
        monkeypatch: _pytest.MonkeyPatch,
    ) -> None:
        """With env var set, should use that directory."""
        monkeypatch.setenv("BRYNHILD_CONFIG_DIR", "/custom/config/dir")
        path = sources.get_user_config_path()
        assert path == _pathlib.Path("/custom/config/dir/config.yaml")

    def test_get_user_config_dir_default(
        self,
        monkeypatch: _pytest.MonkeyPatch,
    ) -> None:
        """Without env var, should return XDG-compliant directory."""
        monkeypatch.delenv("BRYNHILD_CONFIG_DIR", raising=False)
        path = sources.get_user_config_dir()
        assert path == _pathlib.Path.home() / ".config" / "brynhild"

    def test_get_user_config_dir_with_env_var(
        self,
        monkeypatch: _pytest.MonkeyPatch,
    ) -> None:
        """With env var set, should use that directory."""
        monkeypatch.setenv("BRYNHILD_CONFIG_DIR", "/custom/config/dir")
        path = sources.get_user_config_dir()
        assert path == _pathlib.Path("/custom/config/dir")

    def test_get_project_config_path(self) -> None:
        """Should return project-relative config path."""
        project_root = _pathlib.Path("/some/project")
        path = sources.get_project_config_path(project_root)
        assert path == project_root / ".brynhild" / "config.yaml"


# Minimal Settings class for testing
class MinimalSettings(_pydantic_settings.BaseSettings):
    """Minimal settings class for testing DeepChainMapSettingsSource."""

    model_config = _pydantic_settings.SettingsConfigDict(
        env_prefix="TEST_",
        extra="ignore",
    )

    version: int = 0
    name: str = "default"


class NestedSettings(_pydantic_settings.BaseSettings):
    """Settings class with nested structure for testing."""

    model_config = _pydantic_settings.SettingsConfigDict(
        env_prefix="TEST_",
        extra="ignore",
    )

    version: int = 0
    models: dict[str, _typing.Any] = _pydantic.Field(default_factory=dict)
    behavior: dict[str, _typing.Any] = _pydantic.Field(default_factory=dict)


class TestDeepChainMapSettingsSourceLoadFromSingleFile:
    """Tests for loading config from a single file."""

    def test_load_builtin_defaults(self) -> None:
        """Should load built-in defaults config.yaml."""
        source = sources.DeepChainMapSettingsSource(MinimalSettings)
        # Should have loaded the defaults file
        assert source._dcm is not None

    def test_load_returns_dict(self) -> None:
        """__call__ should return a dict."""
        source = sources.DeepChainMapSettingsSource(MinimalSettings)
        result = source()
        assert isinstance(result, dict)

    def test_loaded_values_from_defaults(self) -> None:
        """Should contain values from defaults/config.yaml."""
        source = sources.DeepChainMapSettingsSource(MinimalSettings)
        result = source()
        # Our defaults/config.yaml has version: 1
        assert result.get("version") == 1


class TestDeepChainMapSettingsSourceMergeOrder:
    """Tests for merging multiple config files.
    
    These tests verify that higher-precedence layers OVERRIDE lower-precedence
    layers for scalar values. Precedence order: Project > User > Builtin.
    """

    def test_explicit_override_chain(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Verify the complete override chain: project > user > builtin."""
        # Builtin sets all values
        builtin_config = tmp_path / "builtin.yaml"
        builtin_config.write_text(
            "version: 100\n"
            "name: builtin-name\n"
        )

        # User overrides version only
        user_config = tmp_path / "user.yaml"
        user_config.write_text(
            "version: 200\n"  # OVERRIDES builtin's 100
            # name: not set, should inherit builtin's "builtin-name"
        )

        # Project overrides version again
        project_root = tmp_path / "project"
        project_root.mkdir()
        project_config_dir = project_root / ".brynhild"
        project_config_dir.mkdir()
        project_config_file = project_config_dir / "config.yaml"
        project_config_file.write_text(
            "version: 300\n"  # OVERRIDES user's 200 (which overrode builtin's 100)
            # name: not set, should inherit from user -> builtin
        )

        source = sources.DeepChainMapSettingsSource(
            MinimalSettings,
            project_root=project_root,
            user_config_path=user_config,
            builtin_config_path=builtin_config,
        )
        result = source()

        # OVERRIDE VERIFICATION:
        # - version: builtin=100 -> user=200 -> project=300
        #   Final value should be 300 (project wins)
        assert result.get("version") == 300, (
            "Project should override user which should override builtin"
        )

        # - name: builtin="builtin-name" -> user=<not set> -> project=<not set>
        #   Final value should be "builtin-name" (inherited from builtin)
        assert result.get("name") == "builtin-name", (
            "Should inherit from builtin when user and project don't override"
        )

    def test_project_config_overrides_builtin(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Project config should override built-in defaults."""
        # Create a project config
        project_root = tmp_path / "project"
        project_root.mkdir()
        config_dir = project_root / ".brynhild"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text("version: 99\nname: project-override\n")

        source = sources.DeepChainMapSettingsSource(
            MinimalSettings,
            project_root=project_root,
        )
        result = source()

        # Project config should override defaults
        assert result.get("version") == 99
        assert result.get("name") == "project-override"

    def test_user_config_overrides_builtin(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """User config should override built-in defaults."""
        # Create user config in temp location
        config_file = tmp_path / "user_config.yaml"
        config_file.write_text("version: 42\n")

        # Use explicit path override
        source = sources.DeepChainMapSettingsSource(
            MinimalSettings,
            user_config_path=config_file,
        )
        result = source()

        # User config should override defaults
        assert result.get("version") == 42

    def test_project_overrides_user_overrides_builtin(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Project > User > Builtin precedence."""
        # Create user config
        user_config_file = tmp_path / "user_config.yaml"
        user_config_file.write_text("version: 42\nname: user-name\n")

        # Create project config (only overrides version)
        project_root = tmp_path / "project"
        project_root.mkdir()
        project_config_dir = project_root / ".brynhild"
        project_config_dir.mkdir()
        project_config_file = project_config_dir / "config.yaml"
        project_config_file.write_text("version: 99\n")

        source = sources.DeepChainMapSettingsSource(
            MinimalSettings,
            project_root=project_root,
            user_config_path=user_config_file,
        )
        result = source()

        # Project overrides version, but name comes from user config
        assert result.get("version") == 99
        assert result.get("name") == "user-name"


class TestDeepChainMapSettingsSourceNestedMerge:
    """Tests for nested dictionary merging via DCM.
    
    These tests verify a CORE DESIGN GOAL: layered configs should merge deeply,
    not just override. The merged result should contain values from multiple
    layers that no single config file contains.
    """

    def test_two_layer_nested_merge(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Two configs contributing different nested values should merge."""
        # Create user config with nested dict
        user_config_file = tmp_path / "user_config.yaml"
        user_config_file.write_text(
            "version: 1\n"
            "models:\n"
            "  default: user-model\n"
            "  favorites:\n"
            "    model-a: true\n"
        )

        # Create project config with additional nested values
        project_root = tmp_path / "project"
        project_root.mkdir()
        project_config_dir = project_root / ".brynhild"
        project_config_dir.mkdir()
        project_config_file = project_config_dir / "config.yaml"
        project_config_file.write_text(
            "models:\n"
            "  favorites:\n"
            "    model-b: true\n"
        )

        source = sources.DeepChainMapSettingsSource(
            NestedSettings,
            project_root=project_root,
            user_config_path=user_config_file,
        )
        result = source()

        # CRITICAL: merged result has values from BOTH configs
        # This result is impossible from either config alone
        models = result.get("models", {})
        assert models.get("default") == "user-model"  # from user
        favorites = models.get("favorites", {})
        assert favorites.get("model-a") is True  # from user
        assert favorites.get("model-b") is True  # from project

    def test_three_layer_merge_each_contributes(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """All three layers (builtin, user, project) should contribute unique values."""
        # Builtin: provides base structure
        builtin_config = tmp_path / "builtin.yaml"
        builtin_config.write_text(
            "version: 1\n"
            "models:\n"
            "  favorites:\n"
            "    from-builtin: true\n"
            "behavior:\n"
            "  timeout: 30\n"
        )

        # User: adds to favorites, adds new behavior key
        user_config = tmp_path / "user.yaml"
        user_config.write_text(
            "models:\n"
            "  favorites:\n"
            "    from-user: true\n"
            "behavior:\n"
            "  verbose: true\n"
        )

        # Project: adds to favorites, adds another behavior key
        project_root = tmp_path / "project"
        project_root.mkdir()
        project_config_dir = project_root / ".brynhild"
        project_config_dir.mkdir()
        project_config_file = project_config_dir / "config.yaml"
        project_config_file.write_text(
            "models:\n"
            "  favorites:\n"
            "    from-project: true\n"
            "behavior:\n"
            "  debug: true\n"
        )

        source = sources.DeepChainMapSettingsSource(
            NestedSettings,
            project_root=project_root,
            user_config_path=user_config,
            builtin_config_path=builtin_config,
        )
        result = source()

        # CRITICAL: merged result has values from ALL THREE configs
        # This result is IMPOSSIBLE from any single config file
        models = result.get("models", {})
        favorites = models.get("favorites", {})
        
        # All three layers contributed a unique favorite
        assert favorites.get("from-builtin") is True
        assert favorites.get("from-user") is True
        assert favorites.get("from-project") is True

        # All three layers contributed unique behavior keys
        behavior = result.get("behavior", {})
        assert behavior.get("timeout") == 30    # from builtin
        assert behavior.get("verbose") is True  # from user
        assert behavior.get("debug") is True    # from project

    def test_deep_nested_merge_multiple_levels(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Merge should work at multiple nesting levels."""
        # Builtin: deep structure
        builtin_config = tmp_path / "builtin.yaml"
        builtin_config.write_text(
            "models:\n"
            "  registry:\n"
            "    anthropic:\n"
            "      claude-sonnet:\n"
            "        context: 200000\n"
            "    openai:\n"
            "      gpt-4:\n"
            "        context: 128000\n"
        )

        # User: adds sibling at deep level
        user_config = tmp_path / "user.yaml"
        user_config.write_text(
            "models:\n"
            "  registry:\n"
            "    anthropic:\n"
            "      claude-opus:\n"
            "        context: 200000\n"
        )

        # Project: adds to a different branch
        project_root = tmp_path / "project"
        project_root.mkdir()
        project_config_dir = project_root / ".brynhild"
        project_config_dir.mkdir()
        project_config_file = project_config_dir / "config.yaml"
        project_config_file.write_text(
            "models:\n"
            "  registry:\n"
            "    local:\n"
            "      ollama-llama:\n"
            "        context: 32000\n"
        )

        source = sources.DeepChainMapSettingsSource(
            NestedSettings,
            project_root=project_root,
            user_config_path=user_config,
            builtin_config_path=builtin_config,
        )
        result = source()

        # Verify deep merge at 4 levels: models > registry > provider > model
        models = result.get("models", {})
        registry = models.get("registry", {})

        # From builtin: anthropic.claude-sonnet and openai.gpt-4
        anthropic = registry.get("anthropic", {})
        assert anthropic.get("claude-sonnet", {}).get("context") == 200000

        openai = registry.get("openai", {})
        assert openai.get("gpt-4", {}).get("context") == 128000

        # From user: anthropic.claude-opus (merged with builtin's anthropic)
        assert anthropic.get("claude-opus", {}).get("context") == 200000

        # From project: local.ollama-llama (new branch)
        local = registry.get("local", {})
        assert local.get("ollama-llama", {}).get("context") == 32000

    def test_scalar_override_dict_merge(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Scalar values override while dicts merge at the same level."""
        builtin_config = tmp_path / "builtin.yaml"
        builtin_config.write_text(
            "version: 1\n"  # scalar - will be overridden
            "models:\n"
            "  default: builtin-model\n"  # scalar - will be overridden
            "  favorites:\n"  # dict - will be merged
            "    builtin-fav: true\n"
        )

        user_config = tmp_path / "user.yaml"
        user_config.write_text(
            "version: 2\n"  # scalar override
            "models:\n"
            "  favorites:\n"  # dict merge
            "    user-fav: true\n"
        )

        project_root = tmp_path / "project"
        project_root.mkdir()
        project_config_dir = project_root / ".brynhild"
        project_config_dir.mkdir()
        project_config_file = project_config_dir / "config.yaml"
        project_config_file.write_text(
            "models:\n"
            "  default: project-model\n"  # scalar override
        )

        source = sources.DeepChainMapSettingsSource(
            NestedSettings,
            project_root=project_root,
            user_config_path=user_config,
            builtin_config_path=builtin_config,
        )
        result = source()

        # Scalars: highest precedence wins (project > user > builtin)
        assert result.get("version") == 2  # user overrode builtin, project didn't set
        models = result.get("models", {})
        assert models.get("default") == "project-model"  # project wins

        # Dicts: merged from all layers
        favorites = models.get("favorites", {})
        assert favorites.get("builtin-fav") is True
        assert favorites.get("user-fav") is True


class TestDeepChainMapSettingsSourceMissingFiles:
    """Tests for handling missing config files gracefully."""

    def test_missing_user_config_ok(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Should work fine without user config."""
        # Point to a path that doesn't exist
        missing_config = tmp_path / "nonexistent" / "config.yaml"

        # Should not raise
        source = sources.DeepChainMapSettingsSource(
            MinimalSettings,
            user_config_path=missing_config,
        )
        result = source()
        assert isinstance(result, dict)

    def test_missing_project_config_ok(self, tmp_path: _pathlib.Path) -> None:
        """Should work fine without project config."""
        # Project root exists but no .brynhild/config.yaml
        project_root = tmp_path / "project"
        project_root.mkdir()

        # Should not raise
        source = sources.DeepChainMapSettingsSource(
            MinimalSettings,
            project_root=project_root,
        )
        result = source()
        assert isinstance(result, dict)

    def test_no_project_root_ok(self) -> None:
        """Should work fine with project_root=None."""
        source = sources.DeepChainMapSettingsSource(
            MinimalSettings,
            project_root=None,
        )
        result = source()
        assert isinstance(result, dict)


class TestDeepChainMapSettingsSourceErrorHandling:
    """Tests for error handling in config file loading."""

    def test_malformed_yaml_raises_config_file_error(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Malformed YAML should raise ConfigFileError with clear message."""
        config_file = tmp_path / "bad.yaml"
        config_file.write_text("invalid:\n  - broken\n yaml: [")

        with _pytest.raises(sources.ConfigFileError) as exc_info:
            sources.DeepChainMapSettingsSource(
                MinimalSettings,
                user_config_path=config_file,
            )

        assert "invalid YAML" in str(exc_info.value)
        assert str(config_file) in str(exc_info.value)

    def test_list_at_top_level_raises_config_file_error(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Config file with list at top level should raise clear error."""
        config_file = tmp_path / "list.yaml"
        config_file.write_text("- item1\n- item2\n- item3\n")

        with _pytest.raises(sources.ConfigFileError) as exc_info:
            sources.DeepChainMapSettingsSource(
                MinimalSettings,
                user_config_path=config_file,
            )

        assert "must be a YAML mapping" in str(exc_info.value)
        assert "got list" in str(exc_info.value)

    def test_scalar_at_top_level_raises_config_file_error(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Config file with scalar at top level should raise clear error."""
        config_file = tmp_path / "scalar.yaml"
        config_file.write_text("just a string\n")

        with _pytest.raises(sources.ConfigFileError) as exc_info:
            sources.DeepChainMapSettingsSource(
                MinimalSettings,
                user_config_path=config_file,
            )

        assert "must be a YAML mapping" in str(exc_info.value)
        assert "got str" in str(exc_info.value)

    def test_permission_error_raises_config_file_error(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Unreadable file should raise ConfigFileError."""
        config_file = tmp_path / "unreadable.yaml"
        config_file.write_text("version: 1\n")
        config_file.chmod(0o000)  # Remove all permissions

        try:
            with _pytest.raises(sources.ConfigFileError) as exc_info:
                sources.DeepChainMapSettingsSource(
                    MinimalSettings,
                    user_config_path=config_file,
                )

            assert "permission denied" in str(exc_info.value).lower()
        finally:
            # Restore permissions for cleanup
            config_file.chmod(0o644)

    def test_empty_yaml_ok(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Empty YAML file should be handled gracefully."""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")

        # Should not raise
        source = sources.DeepChainMapSettingsSource(
            MinimalSettings,
            user_config_path=config_file,
        )
        result = source()
        assert isinstance(result, dict)

    def test_config_file_error_includes_path(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """ConfigFileError should include the problematic file path."""
        config_file = tmp_path / "my_config.yaml"
        config_file.write_text("- list\n")

        with _pytest.raises(sources.ConfigFileError) as exc_info:
            sources.DeepChainMapSettingsSource(
                MinimalSettings,
                user_config_path=config_file,
            )

        # Error should include path for easy debugging
        assert exc_info.value.path == config_file
        assert "my_config.yaml" in str(exc_info.value)

    def test_missing_builtin_defaults_raises_error(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Missing builtin defaults should raise clear error, not fail silently.
        
        Builtin defaults are bundled with the package. If they're missing,
        that indicates an installation problem that must be surfaced.
        """
        nonexistent_builtin = tmp_path / "nonexistent" / "defaults.yaml"

        with _pytest.raises(sources.ConfigFileError) as exc_info:
            sources.DeepChainMapSettingsSource(
                MinimalSettings,
                builtin_config_path=nonexistent_builtin,
            )

        assert "built-in defaults not found" in str(exc_info.value)
        assert "installation problem" in str(exc_info.value)

    def test_empty_builtin_defaults_raises_error(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Empty builtin defaults should raise clear error, not fail silently.
        
        Builtin defaults must have content to provide base configuration.
        An empty file indicates an installation or packaging problem.
        """
        empty_builtin = tmp_path / "empty_defaults.yaml"
        empty_builtin.write_text("")

        with _pytest.raises(sources.ConfigFileError) as exc_info:
            sources.DeepChainMapSettingsSource(
                MinimalSettings,
                builtin_config_path=empty_builtin,
            )

        assert "empty" in str(exc_info.value).lower()
        assert "installation problem" in str(exc_info.value)


class TestDeepChainMapSettingsSourceGetFieldValue:
    """Tests for get_field_value method."""

    def test_get_existing_field(self) -> None:
        """Should return value for existing field."""
        source = sources.DeepChainMapSettingsSource(MinimalSettings)
        value, name, is_complex = source.get_field_value(
            MinimalSettings.model_fields["version"],
            "version",
        )
        assert value == 1  # From defaults
        assert name == "version"
        assert is_complex is False

    def test_get_missing_field(self) -> None:
        """Should return None for missing field."""
        source = sources.DeepChainMapSettingsSource(MinimalSettings)
        value, name, is_complex = source.get_field_value(
            MinimalSettings.model_fields["name"],
            "nonexistent_field",
        )
        assert value is None
        assert name == "nonexistent_field"
        assert is_complex is False

    def test_get_complex_field(self) -> None:
        """Should mark dict/list values as complex."""
        source = sources.DeepChainMapSettingsSource(NestedSettings)
        value, name, is_complex = source.get_field_value(
            NestedSettings.model_fields["models"],
            "models",
        )
        # Our defaults has models: { default: ... }
        # DCM returns MutableProxy which is a Mapping
        import collections.abc
        assert isinstance(value, collections.abc.Mapping)
        assert is_complex is True


class TestDeepChainMapSettingsSourcePathOverrides:
    """Tests for explicit path override parameters."""

    def test_builtin_config_path_override(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Should use explicit builtin_config_path when provided."""
        # Create custom builtin config
        custom_builtin = tmp_path / "custom_builtin.yaml"
        custom_builtin.write_text("version: 999\nname: custom-builtin\n")

        source = sources.DeepChainMapSettingsSource(
            MinimalSettings,
            builtin_config_path=custom_builtin,
            user_config_path=tmp_path / "nonexistent.yaml",  # Don't load user config
        )
        result = source()

        assert result.get("version") == 999
        assert result.get("name") == "custom-builtin"

    def test_user_config_path_override(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Should use explicit user_config_path when provided."""
        # Create custom user config
        custom_user = tmp_path / "custom_user.yaml"
        custom_user.write_text("version: 888\nname: custom-user\n")

        source = sources.DeepChainMapSettingsSource(
            MinimalSettings,
            user_config_path=custom_user,
        )
        result = source()

        # User config should override builtin
        assert result.get("version") == 888
        assert result.get("name") == "custom-user"

    def test_env_var_override_for_user_config(
        self,
        tmp_path: _pathlib.Path,
        monkeypatch: _pytest.MonkeyPatch,
    ) -> None:
        """BRYNHILD_CONFIG_DIR env var should override default user config path."""
        # Create config in custom location
        custom_dir = tmp_path / "custom_config_dir"
        custom_dir.mkdir()
        config_file = custom_dir / "config.yaml"
        config_file.write_text("version: 777\nname: from-env-var\n")

        # Set env var
        monkeypatch.setenv("BRYNHILD_CONFIG_DIR", str(custom_dir))

        source = sources.DeepChainMapSettingsSource(MinimalSettings)
        result = source()

        assert result.get("version") == 777
        assert result.get("name") == "from-env-var"

    def test_explicit_path_takes_precedence_over_env_var(
        self,
        tmp_path: _pathlib.Path,
        monkeypatch: _pytest.MonkeyPatch,
    ) -> None:
        """Explicit user_config_path should take precedence over env var."""
        # Create config via env var
        env_dir = tmp_path / "env_config"
        env_dir.mkdir()
        env_config = env_dir / "config.yaml"
        env_config.write_text("version: 111\nname: from-env\n")
        monkeypatch.setenv("BRYNHILD_CONFIG_DIR", str(env_dir))

        # Create config via explicit path
        explicit_config = tmp_path / "explicit_config.yaml"
        explicit_config.write_text("version: 222\nname: from-explicit\n")

        source = sources.DeepChainMapSettingsSource(
            MinimalSettings,
            user_config_path=explicit_config,
        )
        result = source()

        # Explicit should win
        assert result.get("version") == 222
        assert result.get("name") == "from-explicit"


class TestDeepChainMapSettingsSourceUnknownKeys:
    """Tests for unknown key preservation.

    The __call__() method must return ALL keys from merged YAML, not just
    known fields. This enables extra="allow" to capture unknown keys for
    strict validation mode (typo detection).
    """

    def test_unknown_top_level_key_preserved(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Unknown top-level keys should be returned by __call__()."""
        builtin = tmp_path / "builtin.yaml"
        builtin.write_text("version: 1\n")

        user = tmp_path / "user.yaml"
        user.write_text("unknown_key: some_value\ntypo_field: oops\n")

        source = sources.DeepChainMapSettingsSource(
            MinimalSettings,
            builtin_config_path=builtin,
            user_config_path=user,
        )
        result = source()

        # Unknown keys MUST be in the result
        assert "unknown_key" in result
        assert result["unknown_key"] == "some_value"
        assert "typo_field" in result
        assert result["typo_field"] == "oops"

    def test_unknown_nested_keys_preserved(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Unknown keys inside known sections should be preserved."""
        builtin = tmp_path / "builtin.yaml"
        builtin.write_text("version: 1\nbehavior:\n  known: true\n")

        user = tmp_path / "user.yaml"
        user.write_text("behavior:\n  unknown_nested: value\n  typo: oops\n")

        source = sources.DeepChainMapSettingsSource(
            MinimalSettings,
            builtin_config_path=builtin,
            user_config_path=user,
        )
        result = source()

        # behavior section should exist and contain both known and unknown
        assert "behavior" in result
        behavior = result["behavior"]
        assert behavior.get("known") is True
        assert behavior.get("unknown_nested") == "value"
        assert behavior.get("typo") == "oops"

    def test_all_keys_from_all_layers_preserved(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Keys from all layers (builtin, user, project) should be in result."""
        builtin = tmp_path / "builtin.yaml"
        builtin.write_text("version: 1\nbuiltin_only: from_builtin\n")

        user = tmp_path / "user.yaml"
        user.write_text("user_only: from_user\n")

        project_root = tmp_path / "project"
        project_root.mkdir()
        project_config_dir = project_root / ".brynhild"
        project_config_dir.mkdir()
        project_config = project_config_dir / "config.yaml"
        project_config.write_text("project_only: from_project\n")

        source = sources.DeepChainMapSettingsSource(
            MinimalSettings,
            project_root=project_root,
            builtin_config_path=builtin,
            user_config_path=user,
        )
        result = source()

        # All keys from all layers should be present
        assert result.get("version") == 1
        assert result.get("builtin_only") == "from_builtin"
        assert result.get("user_only") == "from_user"
        assert result.get("project_only") == "from_project"
