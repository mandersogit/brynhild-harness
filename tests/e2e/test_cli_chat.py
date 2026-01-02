"""
End-to-end tests for CLI chat command.

Tests the `brynhild chat` command for conversational interactions.
"""

import json as _json

import click.testing as _click_testing
import pytest as _pytest

import brynhild.cli as cli
import tests.conftest as conftest


@_pytest.mark.e2e
def test_chat_no_prompt_exits_with_error(
    cli_runner: _click_testing.CliRunner,
) -> None:
    """CLI chat without prompt exits with error."""
    result = cli_runner.invoke(cli.cli, ["chat"])

    assert result.exit_code != 0
    assert "no prompt" in result.output.lower() or "error" in result.output.lower()


@_pytest.mark.e2e
def test_chat_no_prompt_json_shows_error(
    cli_runner: _click_testing.CliRunner,
) -> None:
    """CLI chat --json without prompt returns JSON error."""
    result = cli_runner.invoke(cli.cli, ["chat", "--json"])

    assert result.exit_code != 0

    # Should output valid JSON with error
    data = _json.loads(result.output)
    assert "error" in data


@_pytest.mark.e2e
def test_chat_print_mode_outputs_response(
    cli_runner: _click_testing.CliRunner,
    monkeypatch: _pytest.MonkeyPatch,
) -> None:
    """CLI chat -p outputs response to stdout."""
    # Create a mock provider with default response
    mock_provider = conftest.MockProvider()

    # Patch create_provider to return our mock
    def mock_create_provider(**kwargs: object) -> conftest.MockProvider:  # noqa: ARG001
        return mock_provider

    monkeypatch.setattr("brynhild.api.create_provider", mock_create_provider)

    result = cli_runner.invoke(
        cli.cli,
        ["chat", "-p", "Hello"],
    )

    assert result.exit_code == 0
    # The mock provider returns "mock response"
    assert "mock response" in result.output or "Assistant" in result.output


@_pytest.mark.e2e
def test_chat_json_mode_returns_valid_json(
    cli_runner: _click_testing.CliRunner,
    monkeypatch: _pytest.MonkeyPatch,
) -> None:
    """CLI chat --json returns valid JSON response."""
    # Create a mock provider with default response (no custom responses needed)
    mock_provider = conftest.MockProvider()

    def mock_create_provider(**kwargs: object) -> conftest.MockProvider:  # noqa: ARG001
        return mock_provider

    monkeypatch.setattr("brynhild.api.create_provider", mock_create_provider)

    result = cli_runner.invoke(
        cli.cli,
        ["chat", "--json", "What is 2+2?"],
    )

    assert result.exit_code == 0

    # Should be valid JSON
    data = _json.loads(result.output)

    # Should have response content (the JSON renderer outputs "response" field)
    assert "response" in data or "content" in data or "text" in data


@_pytest.mark.e2e
def test_chat_no_tools_flag_disables_tools(
    cli_runner: _click_testing.CliRunner,
    monkeypatch: _pytest.MonkeyPatch,
) -> None:
    """CLI chat --no-tools disables tool use."""
    # Create a mock provider with default response
    mock_provider = conftest.MockProvider()

    def mock_create_provider(**kwargs: object) -> conftest.MockProvider:  # noqa: ARG001
        return mock_provider

    monkeypatch.setattr("brynhild.api.create_provider", mock_create_provider)

    result = cli_runner.invoke(
        cli.cli,
        ["chat", "--no-tools", "--json", "Run ls command"],
    )

    assert result.exit_code == 0

    # The conversation should complete without tool execution
    data = _json.loads(result.output)
    # Should have a response (not a tool call error)
    assert "error" not in data or data.get("error") is None
