"""
End-to-end tests for CLI tools commands.

Tests the `brynhild tools` subcommands.
"""

import json as _json

import click.testing as _click_testing
import pytest as _pytest

import brynhild.cli as cli


@_pytest.mark.e2e
def test_tools_list_shows_all_tools(
    cli_runner: _click_testing.CliRunner,
) -> None:
    """CLI tools list command shows available tools."""
    result = cli_runner.invoke(cli.cli, ["tools", "list"])

    assert result.exit_code == 0
    # Should list the core tools
    assert "Bash" in result.output
    assert "Read" in result.output
    assert "Write" in result.output
    assert "Edit" in result.output


@_pytest.mark.e2e
def test_tools_list_json_is_valid(
    cli_runner: _click_testing.CliRunner,
) -> None:
    """CLI tools list --json outputs valid JSON array."""
    result = cli_runner.invoke(cli.cli, ["tools", "list", "--json"])

    assert result.exit_code == 0

    # Should be valid JSON
    data = _json.loads(result.output)

    # Should be a list of tool objects
    assert isinstance(data, list)
    assert len(data) > 0

    # Each tool should have expected fields
    tool_names = [t["name"] for t in data]
    assert "Bash" in tool_names
    assert "Read" in tool_names


@_pytest.mark.e2e
def test_tools_schema_shows_json_schema(
    cli_runner: _click_testing.CliRunner,
) -> None:
    """CLI tools schema command shows tool input schema."""
    result = cli_runner.invoke(cli.cli, ["tools", "schema", "Bash"])

    assert result.exit_code == 0

    # Should be valid JSON
    data = _json.loads(result.output)

    # Bash tool should have name and input_schema
    assert data["name"] == "Bash"
    assert "input_schema" in data
    assert "command" in data["input_schema"]["properties"]
