"""Tests for configuration settings."""

import os as _os
import pathlib as _pathlib
import unittest.mock as _mock

import pytest as _pytest

import brynhild.config as config
import brynhild.config.types as types

# Keys to clear from environment for isolated tests
# Note: With nested config, env vars use __ delimiter (e.g., BRYNHILD_BEHAVIOR__VERBOSE)
ENV_KEYS_TO_CLEAR = [
    "OPENROUTER_API_KEY",
    "BRYNHILD_PROVIDERS__DEFAULT",
    "BRYNHILD_MODELS__DEFAULT",
    "BRYNHILD_BEHAVIOR__VERBOSE",
    "BRYNHILD_BEHAVIOR__MAX_TOKENS",
    # Legacy flat keys (no longer used but clear them for test isolation)
    "BRYNHILD_PROVIDER",
    "BRYNHILD_MODEL",
    "BRYNHILD_VERBOSE",
    "BRYNHILD_MAX_TOKENS",
]


def clean_env() -> dict[str, str]:
    """Return environment dict with test-related keys removed."""
    return {k: v for k, v in _os.environ.items() if k not in ENV_KEYS_TO_CLEAR}


class TestSettingsDefaults:
    """Test Settings default values when environment is clean."""

    def test_default_provider_is_openrouter(self) -> None:
        """Default provider should be 'openrouter' when no env override."""
        with _mock.patch.dict(_os.environ, clean_env(), clear=True):
            settings = config.Settings.construct_without_dotenv()
            assert settings.provider == "openrouter"

    def test_default_model_from_builtin_config(self) -> None:
        """Default model should come from built-in config.yaml."""
        with _mock.patch.dict(_os.environ, clean_env(), clear=True):
            settings = config.Settings.construct_without_dotenv()
            # Default from defaults/config.yaml
            assert settings.model == "anthropic/claude-sonnet-4"

    def test_default_output_format_is_text(self) -> None:
        """Default output format should be 'text'."""
        with _mock.patch.dict(_os.environ, clean_env(), clear=True):
            settings = config.Settings.construct_without_dotenv()
            assert settings.output_format == "text"

    def test_default_max_tokens_is_8192(self) -> None:
        """Default max_tokens should be 8192."""
        with _mock.patch.dict(_os.environ, clean_env(), clear=True):
            settings = config.Settings.construct_without_dotenv()
            assert settings.max_tokens == 8192

    def test_default_verbose_is_false(self) -> None:
        """Verbose should be False by default."""
        with _mock.patch.dict(_os.environ, clean_env(), clear=True):
            settings = config.Settings.construct_without_dotenv()
            assert settings.verbose is False

    def test_default_skip_permissions_is_false(self) -> None:
        """dangerously_skip_permissions should be False by default."""
        with _mock.patch.dict(_os.environ, clean_env(), clear=True):
            settings = config.Settings.construct_without_dotenv()
            assert settings.dangerously_skip_permissions is False


class TestSettingsProviders:
    """Test provider-related settings behavior."""

    def test_provider_accepts_valid_values(self) -> None:
        """All valid provider values should be accepted."""
        # Currently supported + planned providers
        valid_providers = ["openrouter", "ollama", "vllm", "vertex"]
        for provider in valid_providers:
            # Must set via nested config structure
            settings = config.Settings.construct_without_dotenv(
                providers=types.ProvidersConfig(default=provider)
            )
            assert settings.provider == provider

    def test_get_api_key_returns_openrouter_key(self) -> None:
        """get_api_key() should return OPENROUTER_API_KEY."""
        with _mock.patch.dict(
            _os.environ, {"OPENROUTER_API_KEY": "test-openrouter-key"}, clear=False
        ):
            settings = config.Settings.construct_without_dotenv(provider="openrouter")
            assert settings.get_api_key() == "test-openrouter-key"

    def test_get_api_key_returns_none_when_key_not_set(self) -> None:
        """get_api_key() should return None when no API key is configured."""
        with _mock.patch.dict(_os.environ, clean_env(), clear=True):
            settings = config.Settings.construct_without_dotenv()
            assert settings.get_api_key() is None


class TestSettingsEnvironmentOverride:
    """Test that environment variables properly override defaults."""

    def test_nested_env_var_overrides_verbose(self) -> None:
        """BRYNHILD_BEHAVIOR__VERBOSE=true should set verbose to True."""
        with _mock.patch.dict(
            _os.environ, {"BRYNHILD_BEHAVIOR__VERBOSE": "true"}, clear=False
        ):
            settings = config.Settings.construct_without_dotenv()
            assert settings.verbose is True

    def test_nested_env_var_overrides_provider(self) -> None:
        """BRYNHILD_PROVIDERS__DEFAULT should override default provider."""
        with _mock.patch.dict(
            _os.environ, {"BRYNHILD_PROVIDERS__DEFAULT": "ollama"}, clear=False
        ):
            settings = config.Settings.construct_without_dotenv()
            assert settings.provider == "ollama"

    def test_nested_env_var_overrides_model(self) -> None:
        """BRYNHILD_MODELS__DEFAULT should override default model."""
        with _mock.patch.dict(
            _os.environ, {"BRYNHILD_MODELS__DEFAULT": "my-custom/model"}, clear=False
        ):
            settings = config.Settings.construct_without_dotenv()
            assert settings.model == "my-custom/model"


class TestSettingsValidation:
    """Test settings validation logic."""

    def test_max_tokens_rejects_zero(self) -> None:
        """max_tokens=0 should raise ValidationError."""
        with _pytest.raises(ValueError):
            # Must pass via nested config
            config.Settings.construct_without_dotenv(
                behavior=types.BehaviorConfig(max_tokens=0)
            )

    def test_max_tokens_rejects_over_limit(self) -> None:
        """max_tokens over 200000 should raise ValidationError."""
        with _pytest.raises(ValueError):
            config.Settings.construct_without_dotenv(
                behavior=types.BehaviorConfig(max_tokens=300000)
            )

    def test_max_tokens_accepts_valid_values(self) -> None:
        """Valid max_tokens values should be accepted."""
        for value in [1, 100, 8192, 200000]:
            settings = config.Settings.construct_without_dotenv(
                behavior=types.BehaviorConfig(max_tokens=value)
            )
            assert settings.max_tokens == value


class TestSettingsSerialization:
    """Test settings serialization to dict."""

    def test_to_dict_includes_all_required_keys(self) -> None:
        """to_dict() should include all configuration keys."""
        settings = config.Settings.construct_without_dotenv()
        d = settings.to_dict()
        required_keys = [
            "provider",
            "model",
            "output_format",
            "max_tokens",
            "verbose",
            "has_api_key",
            "config_dir",
            "project_root",
            "sessions_dir",
        ]
        for key in required_keys:
            assert key in d, f"Key '{key}' missing from to_dict()"

    def test_to_dict_has_api_key_is_boolean(self) -> None:
        """to_dict()['has_api_key'] should be a boolean."""
        settings = config.Settings.construct_without_dotenv()
        d = settings.to_dict()
        assert isinstance(d["has_api_key"], bool)


class TestSettingsDirectories:
    """Test directory-related settings properties."""

    def test_config_dir_follows_xdg(self) -> None:
        """config_dir should follow XDG standard (~/.config/brynhild)."""
        settings = config.Settings.construct_without_dotenv()
        # XDG: ~/.config/brynhild (parent is ~/.config, not ~)
        expected = _pathlib.Path.home() / ".config" / "brynhild"
        assert settings.config_dir == expected

    def test_sessions_dir_is_under_config_dir(self) -> None:
        """sessions_dir should be a subdirectory of config_dir."""
        settings = config.Settings.construct_without_dotenv()
        assert settings.sessions_dir.parent == settings.config_dir


class TestFindGitRoot:
    """Tests for find_git_root() function."""

    def test_returns_path_with_git_directory(self) -> None:
        """When called in a git repo, should return path containing .git."""
        root = config.find_git_root()
        # This test runs inside the brynhild repo, so should find it
        if root is not None:
            assert (root / ".git").exists()

    def test_returns_none_for_non_git_directory(self, tmp_path: _pathlib.Path) -> None:
        """For a directory not in a git repo, should return None."""
        # tmp_path is a fresh temp directory, not a git repo
        result = config.find_git_root(tmp_path)
        assert result is None


class TestFindProjectRoot:
    """Tests for find_project_root() function."""

    def test_finds_directory_containing_pyproject_toml(self, tmp_path: _pathlib.Path) -> None:
        """Should find directory containing pyproject.toml marker."""
        # Create pyproject.toml in tmp_path
        (tmp_path / "pyproject.toml").touch()
        # Create nested subdirectory
        subdir = tmp_path / "src" / "pkg"
        subdir.mkdir(parents=True)

        # From subdir, should find tmp_path as project root
        result = config.find_project_root(subdir)
        assert result == tmp_path

    def test_finds_directory_containing_setup_py(self, tmp_path: _pathlib.Path) -> None:
        """Should find directory containing setup.py marker."""
        (tmp_path / "setup.py").touch()
        subdir = tmp_path / "lib"
        subdir.mkdir()

        result = config.find_project_root(subdir)
        assert result == tmp_path

    def test_returns_cwd_when_no_markers_found(self, tmp_path: _pathlib.Path) -> None:
        """When no project markers found, should return current working directory."""
        # Create empty nested directory with no markers
        empty_dir = tmp_path / "some" / "empty" / "path"
        empty_dir.mkdir(parents=True)

        # Should return cwd as fallback (since no markers found going up)
        result = config.find_project_root(empty_dir)
        # The function returns Path.cwd() as ultimate fallback
        assert result == _pathlib.Path.cwd()

    def test_finds_nearest_marker_walking_up(self, tmp_path: _pathlib.Path) -> None:
        """Should find the nearest project marker when walking up directories."""
        # Create nested project structure
        outer = tmp_path / "outer"
        outer.mkdir()
        (outer / "pyproject.toml").touch()

        inner = outer / "inner"
        inner.mkdir()
        (inner / "pyproject.toml").touch()

        deep = inner / "src" / "pkg"
        deep.mkdir(parents=True)

        # From deep, should find inner (nearest) not outer
        result = config.find_project_root(deep)
        assert result == inner


class TestProjectRootTooWideError:
    """Tests for ProjectRootTooWideError and allow_wide_root behavior."""

    def test_raises_when_root_is_home_directory(self, tmp_path: _pathlib.Path) -> None:
        """Should raise when project root would be ~."""
        # Mock Path.home() to return tmp_path (simulates being at ~)
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        # Mock the home directory and cwd to both be the empty dir
        with (
            _mock.patch.object(_pathlib.Path, "home", return_value=tmp_path),
            _mock.patch.object(_pathlib.Path, "cwd", return_value=tmp_path),
            _pytest.raises(config.ProjectRootTooWideError) as exc_info,
        ):
            config.find_project_root(tmp_path, allow_wide_root=False)
        assert "too broad" in str(exc_info.value).lower()

    def test_raises_when_root_is_filesystem_root(self) -> None:
        """Should raise when project root would be /."""
        # The root directory "/" has no project markers
        # We mock cwd to return / as the fallback
        with _mock.patch.object(_pathlib.Path, "cwd", return_value=_pathlib.Path("/")):
            with _pytest.raises(config.ProjectRootTooWideError) as exc_info:
                # A non-existent path in /tmp will have no markers
                config.find_project_root(_pathlib.Path("/nonexistent"), allow_wide_root=False)
            assert "too broad" in str(exc_info.value).lower()

    def test_allows_wide_root_when_explicitly_permitted(self, tmp_path: _pathlib.Path) -> None:
        """Should not raise when allow_wide_root=True."""
        # Mock home directory to be tmp_path
        with (
            _mock.patch.object(_pathlib.Path, "home", return_value=tmp_path),
            _mock.patch.object(_pathlib.Path, "cwd", return_value=tmp_path),
        ):
            # Should NOT raise when allow_wide_root=True
            result = config.find_project_root(tmp_path, allow_wide_root=True)
            assert result == tmp_path

    def test_settings_allow_home_directory_default_false(self) -> None:
        """allow_home_directory should default to False."""
        with _mock.patch.dict(_os.environ, clean_env(), clear=True):
            settings = config.Settings.construct_without_dotenv()
            assert settings.allow_home_directory is False

    def test_settings_allow_home_directory_from_env(self) -> None:
        """allow_home_directory can be overridden via environment."""
        env = clean_env()
        env["BRYNHILD_ALLOW_HOME_DIRECTORY"] = "true"
        with _mock.patch.dict(_os.environ, env, clear=True):
            settings = config.Settings.construct_without_dotenv()
            assert settings.allow_home_directory is True
