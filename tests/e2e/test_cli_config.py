"""
End-to-end tests for CLI config command.

Tests the `brynhild config` command group for showing configuration.
"""

import json as _json

import click.testing as _click_testing
import pytest as _pytest

import brynhild.cli as cli


@_pytest.mark.e2e
def test_config_displays_overview(
    cli_runner: _click_testing.CliRunner,
) -> None:
    """CLI config command (no subcommand) displays overview."""
    result = cli_runner.invoke(cli.cli, ["config"])

    assert result.exit_code == 0
    # Should show key configuration fields
    assert "provider" in result.output.lower()
    assert "model" in result.output.lower()
    # Should hint at config show command
    assert "config show" in result.output


@_pytest.mark.e2e
def test_config_show_outputs_yaml(
    cli_runner: _click_testing.CliRunner,
) -> None:
    """CLI config show outputs full config as YAML."""
    result = cli_runner.invoke(cli.cli, ["config", "show"])

    assert result.exit_code == 0
    # Should contain main config sections (YAML format)
    assert "models:" in result.output
    assert "providers:" in result.output
    assert "behavior:" in result.output


@_pytest.mark.e2e
def test_config_show_json_is_valid(
    cli_runner: _click_testing.CliRunner,
) -> None:
    """CLI config show --json outputs valid JSON with expected fields."""
    result = cli_runner.invoke(cli.cli, ["config", "show", "--json"])

    assert result.exit_code == 0

    # Should be valid JSON
    data = _json.loads(result.output)

    # Should contain expected top-level sections
    assert "models" in data
    assert "providers" in data
    assert "behavior" in data


@_pytest.mark.e2e
def test_config_path_lists_files(
    cli_runner: _click_testing.CliRunner,
) -> None:
    """CLI config path lists configuration file locations."""
    result = cli_runner.invoke(cli.cli, ["config", "path"])

    assert result.exit_code == 0
    # Should list built-in defaults (always exists)
    assert "Built-in defaults" in result.output
