"""Tests for CLI main module."""

import json as _json
import os as _os
import unittest.mock as _mock

import click.testing as _click_testing

import brynhild.cli as cli


class TestCLIBasics:
    """Test basic CLI functionality (no API key required)."""

    def setup_method(self) -> None:
        """Set up test fixtures with clean environment."""
        # Remove all API keys and brynhild settings from environment
        clean_env = {
            k: v
            for k, v in _os.environ.items()
            if not k.startswith("BRYNHILD_") and not k.endswith("_API_KEY")
        }
        self.runner = _click_testing.CliRunner(env=clean_env)

    def test_help_shows_all_commands(self) -> None:
        """Help output should list all available commands."""
        result = self.runner.invoke(cli.cli, ["--help"])
        assert result.exit_code == 0
        assert "Brynhild" in result.output
        # Verify all main commands are listed
        for cmd in ["chat", "config", "api", "session"]:
            assert cmd in result.output, f"Command '{cmd}' missing from help"

    def test_version_shows_current_version(self) -> None:
        """Version flag should show the package version."""
        result = self.runner.invoke(cli.cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_config_displays_all_fields(self) -> None:
        """Config command should display all configuration fields."""
        result = self.runner.invoke(cli.cli, ["config"])
        assert result.exit_code == 0
        required_fields = ["Provider:", "Model:", "Project Root:", "Config Dir:"]
        for field in required_fields:
            assert field in result.output, f"Field '{field}' missing from config output"

    def test_config_show_outputs_yaml(self) -> None:
        """Config show command should output full config as YAML."""
        result = self.runner.invoke(cli.cli, ["config", "show"])
        assert result.exit_code == 0
        # Should contain main config sections
        assert "models:" in result.output
        assert "providers:" in result.output
        assert "behavior:" in result.output

    def test_config_show_json_contains_all_sections(self) -> None:
        """Config show --json should output full config as JSON."""
        result = self.runner.invoke(cli.cli, ["config", "show", "--json"])
        assert result.exit_code == 0
        data = _json.loads(result.output)
        # Should contain main config sections
        assert "models" in data
        assert "providers" in data
        assert "behavior" in data

    def test_config_show_section_filters_output(self) -> None:
        """Config show --section should filter to specific section."""
        result = self.runner.invoke(cli.cli, ["config", "show", "--section", "models"])
        assert result.exit_code == 0
        assert "models:" in result.output
        # Should NOT contain other sections
        assert "providers:" not in result.output

    def test_config_show_invalid_section_fails(self) -> None:
        """Config show with invalid section should fail with clear error."""
        result = self.runner.invoke(cli.cli, ["config", "show", "--section", "nonexistent"])
        assert result.exit_code != 0
        assert "Unknown section" in result.output

    def test_config_show_provenance_outputs_sources(self) -> None:
        """Config show --provenance should include source information."""
        result = self.runner.invoke(cli.cli, ["config", "show", "--provenance"])
        assert result.exit_code == 0
        # Should have the legend header
        assert "# Sources:" in result.output
        assert "[builtin]" in result.output
        # Should have provenance codes on values (builtin, env, default)
        assert "# [builtin]" in result.output
        # Should show env/auto sources in legend
        assert "[env]" in result.output
        assert "[auto]" in result.output

    def test_config_path_shows_files(self) -> None:
        """Config path command should list configuration file locations."""
        result = self.runner.invoke(cli.cli, ["config", "path"])
        assert result.exit_code == 0
        # Should show built-in defaults (always exists)
        assert "Built-in defaults" in result.output
        assert "✓" in result.output  # At least built-in should exist

    def test_config_path_all_shows_missing_files(self) -> None:
        """Config path --all should show all paths even if not found."""
        result = self.runner.invoke(cli.cli, ["config", "path", "--all"])
        assert result.exit_code == 0
        # Should show user config (may or may not exist)
        assert "User config" in result.output

    def test_provider_option_overrides_default(self) -> None:
        """--provider option should override the default provider."""
        result = self.runner.invoke(
            cli.cli, ["--provider", "openrouter", "config", "show", "--json"]
        )
        assert result.exit_code == 0
        data = _json.loads(result.output)
        assert data["providers"]["default"] == "openrouter"

    def test_model_option_overrides_default(self) -> None:
        """--model option should override the default model."""
        result = self.runner.invoke(
            cli.cli, ["--model", "custom-model", "config", "show", "--json"]
        )
        assert result.exit_code == 0
        data = _json.loads(result.output)
        assert data["models"]["default"] == "custom-model"

    def test_provider_option_accepts_any_valid_provider(self) -> None:
        """--provider should accept any known provider (builtin or plugin)."""
        # Test with ollama (builtin, was previously missing from click.Choice list)
        result = self.runner.invoke(
            cli.cli, ["--provider", "ollama", "config", "show", "--json"]
        )
        assert result.exit_code == 0
        data = _json.loads(result.output)
        assert data["providers"]["default"] == "ollama"

    def test_provider_option_rejects_unknown_provider(self) -> None:
        """--provider should reject unknown provider with helpful error."""
        result = self.runner.invoke(
            cli.cli, ["--provider", "nonexistent-provider", "config"]
        )
        assert result.exit_code != 0
        # Should mention the unknown provider
        assert "nonexistent-provider" in result.output
        # Should list available providers
        assert "Available:" in result.output
        assert "openrouter" in result.output

    def test_chat_without_prompt_fails_with_clear_error(self) -> None:
        """Chat command without prompt should fail with helpful error message."""
        result = self.runner.invoke(cli.cli, ["chat"])
        assert result.exit_code == 1
        assert "No prompt provided" in result.output


class TestCLIWithoutAPIKey:
    """Test CLI behavior when no API key is configured."""

    def setup_method(self) -> None:
        """Set up test fixtures with NO API keys."""
        # Explicitly remove all API keys
        clean_env = {
            k: v
            for k, v in _os.environ.items()
            if not k.endswith("_API_KEY") and not k.startswith("BRYNHILD_")
        }
        self.runner = _click_testing.CliRunner(env=clean_env)

    def test_api_test_reports_missing_key(self) -> None:
        """API test should report missing API key when none configured."""
        # Monkeypatch Settings to not read .env file
        with _mock.patch("brynhild.config.Settings") as MockSettings:
            mock_settings = _mock.MagicMock()
            mock_settings.provider = "anthropic"
            mock_settings.model = "claude-sonnet-4"
            mock_settings.get_api_key.return_value = None
            mock_settings.sessions_dir = "/tmp/sessions"
            MockSettings.return_value = mock_settings

            result = self.runner.invoke(cli.cli, ["api", "test", "--json"])
            assert result.exit_code == 0
            data = _json.loads(result.output)
            assert data["status"] == "missing_api_key"
            assert data["api_key_configured"] is False

    def test_chat_fails_without_api_key(self) -> None:
        """Chat should fail with clear error when no API key is configured."""
        # Mock create_provider to raise the expected error
        with _mock.patch("brynhild.api.create_provider") as mock_create:
            mock_create.side_effect = ValueError(
                "OPENROUTER_API_KEY not found. Set OPENROUTER_API_KEY environment variable."
            )

            result = self.runner.invoke(cli.cli, ["chat", "test prompt"])
            assert result.exit_code == 1
            # Error message mentions API key is required
            assert "api" in result.output.lower() or "key" in result.output.lower()

    def test_chat_json_fails_with_error_object(self) -> None:
        """Chat JSON should return error object when no API key configured."""
        # Mock create_provider to raise the expected error
        with _mock.patch("brynhild.api.create_provider") as mock_create:
            mock_create.side_effect = ValueError(
                "OPENROUTER_API_KEY not found. Set OPENROUTER_API_KEY environment variable."
            )

            result = self.runner.invoke(cli.cli, ["chat", "--json", "test prompt"])
            assert result.exit_code == 1
            data = _json.loads(result.output)
            assert "error" in data
            # Error message mentions API key requirement
            assert "api" in data["error"].lower() or "key" in data["error"].lower()


class TestSessionCLI:
    """Test session CLI commands."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        clean_env = {
            k: v
            for k, v in _os.environ.items()
            if not k.startswith("BRYNHILD_") and not k.endswith("_API_KEY")
        }
        self.runner = _click_testing.CliRunner(env=clean_env)

    def test_session_list_empty_shows_message(self) -> None:
        """Session list with no sessions should show informative message."""
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(cli.cli, ["session", "list"])
            assert result.exit_code == 0
            assert "No sessions found" in result.output

    def test_session_list_json_empty_returns_empty_array(self) -> None:
        """Session list JSON with no sessions should return empty array."""
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(cli.cli, ["session", "list", "--json"])
            assert result.exit_code == 0
            data = _json.loads(result.output)
            assert data == []

    def test_session_show_nonexistent_fails(self) -> None:
        """Session show for nonexistent ID should fail with exit code 1."""
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(cli.cli, ["session", "show", "nonexistent"])
            assert result.exit_code == 1

    def test_session_show_nonexistent_json_returns_error(self) -> None:
        """Session show JSON for nonexistent ID should return error object."""
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(cli.cli, ["session", "show", "nonexistent", "--json"])
            assert result.exit_code == 1
            data = _json.loads(result.output)
            assert "error" in data
            assert "nonexistent" in data["error"]

    def test_session_delete_nonexistent_fails(self) -> None:
        """Session delete for nonexistent ID should fail with exit code 1."""
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(cli.cli, ["session", "delete", "nonexistent", "--yes"])
            assert result.exit_code == 1
