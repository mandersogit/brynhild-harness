"""
End-to-end tests for CLI session commands.

Tests the `brynhild session` subcommands.
"""

import json as _json

import click.testing as _click_testing
import pytest as _pytest

import brynhild.cli as cli


@_pytest.mark.e2e
def test_session_list_runs_successfully(
    cli_runner: _click_testing.CliRunner,
) -> None:
    """CLI session list command runs without error."""
    result = cli_runner.invoke(cli.cli, ["session", "list"])

    assert result.exit_code == 0
    # Should either show sessions or "No sessions found."
    assert "sessions" in result.output.lower() or "No sessions found" in result.output


@_pytest.mark.e2e
def test_session_list_json_is_valid(
    cli_runner: _click_testing.CliRunner,
) -> None:
    """CLI session list --json outputs valid JSON array."""
    result = cli_runner.invoke(cli.cli, ["session", "list", "--json"])

    assert result.exit_code == 0

    # Should be valid JSON array
    data = _json.loads(result.output)
    assert isinstance(data, list)
