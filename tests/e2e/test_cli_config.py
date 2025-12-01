"""
End-to-end tests for CLI config command.

Tests the `brynhild config` command for showing configuration.
"""

import json as _json

import click.testing as _click_testing
import pytest as _pytest

import brynhild.cli as cli


@_pytest.mark.e2e
def test_config_show_displays_settings(
    cli_runner: _click_testing.CliRunner,
) -> None:
    """CLI config command displays current settings."""
    result = cli_runner.invoke(cli.cli, ["config"])

    assert result.exit_code == 0
    # Should show key configuration fields
    assert "provider" in result.output.lower()
    assert "model" in result.output.lower()


@_pytest.mark.e2e
def test_config_show_json_is_valid(
    cli_runner: _click_testing.CliRunner,
) -> None:
    """CLI config --json outputs valid JSON with expected fields."""
    result = cli_runner.invoke(cli.cli, ["config", "--json"])

    assert result.exit_code == 0

    # Should be valid JSON
    data = _json.loads(result.output)

    # Should contain expected fields
    assert "provider" in data
    assert "model" in data
    assert "config_dir" in data

