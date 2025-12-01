"""
End-to-end tests for CLI hooks commands.

Tests the `brynhild hooks` subcommands.
"""

import pathlib as _pathlib

import click.testing as _click_testing
import pytest as _pytest

import brynhild.cli as cli


@_pytest.mark.e2e
def test_hooks_list_shows_configured_hooks(
    cli_runner: _click_testing.CliRunner,
    tmp_path: _pathlib.Path,
    monkeypatch: _pytest.MonkeyPatch,
) -> None:
    """CLI hooks list command shows configured hooks."""
    # Create project with hooks
    brynhild_dir = tmp_path / ".brynhild"
    brynhild_dir.mkdir()

    hooks_yaml = brynhild_dir / "hooks.yaml"
    hooks_yaml.write_text("""
version: 1
hooks:
  pre_tool_use:
    - name: test_hook
      type: command
      command: "echo test"
""")

    # Change to the temp directory
    monkeypatch.chdir(tmp_path)

    result = cli_runner.invoke(cli.cli, ["hooks", "list"])

    assert result.exit_code == 0
    # Should show the hook we configured
    assert "test_hook" in result.output or "pre_tool_use" in result.output


@_pytest.mark.e2e
def test_hooks_validate_reports_valid(
    cli_runner: _click_testing.CliRunner,
    tmp_path: _pathlib.Path,
) -> None:
    """CLI hooks validate reports valid config."""
    # Create a valid hooks config
    hooks_yaml = tmp_path / "hooks.yaml"
    hooks_yaml.write_text("""
version: 1
hooks:
  pre_tool_use:
    - name: valid_hook
      type: command
      command: "echo valid"
""")

    result = cli_runner.invoke(
        cli.cli, ["hooks", "validate", str(hooks_yaml)]
    )

    assert result.exit_code == 0
    # Should indicate success
    assert "valid" in result.output.lower() or "ok" in result.output.lower()


@_pytest.mark.e2e
def test_hooks_validate_reports_errors(
    cli_runner: _click_testing.CliRunner,
    tmp_path: _pathlib.Path,
) -> None:
    """CLI hooks validate reports errors for invalid config."""
    # Create an invalid hooks config (missing required fields)
    hooks_yaml = tmp_path / "invalid_hooks.yaml"
    hooks_yaml.write_text("""
version: 1
hooks:
  pre_tool_use:
    - name: invalid_hook
      # Missing type field
""")

    result = cli_runner.invoke(
        cli.cli, ["hooks", "validate", str(hooks_yaml)]
    )

    # Should report an error (either non-zero exit or error message)
    # The exact behavior depends on implementation
    assert result.exit_code != 0 or "error" in result.output.lower()

