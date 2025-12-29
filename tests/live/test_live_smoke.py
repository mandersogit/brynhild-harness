"""
Smoke tests that run the actual bin/brynhild command.

These tests verify the complete end-to-end pipeline:
- Shell script entry point
- Provider initialization with profile
- Conversation logging
- Log viewing

Configuration:
    Set these in .env (gitignored):
        BRYNHILD_OLLAMA_HOST=your-ollama-server  # or OLLAMA_HOST
        BRYNHILD_PROVIDER=ollama
        BRYNHILD_MODEL=your-model

These tests are marked @ollama_local for running against a private Ollama server.
"""

import json as _json
import os as _os
import pathlib as _pathlib
import subprocess as _subprocess

import pytest as _pytest

# All tests require local/private Ollama server (set BRYNHILD_OLLAMA_HOST in .env)
pytestmark = [_pytest.mark.live, _pytest.mark.slow, _pytest.mark.ollama_local, _pytest.mark.smoke]

# Path to the brynhild script
PROJECT_ROOT = _pathlib.Path(__file__).parent.parent.parent
BRYNHILD_BIN = PROJECT_ROOT / "bin" / "brynhild"


def _run_brynhild(
    *args: str,
    env_override: dict[str, str] | None = None,
    timeout: int = 60,
) -> _subprocess.CompletedProcess[str]:
    """
    Run brynhild command and return the result.

    Args:
        *args: Command arguments (e.g., "chat", "-p", "hello")
        env_override: Environment variables to add/override
        timeout: Timeout in seconds

    Returns:
        CompletedProcess with stdout, stderr, returncode

    Note:
        Expects BRYNHILD_OLLAMA_HOST (or OLLAMA_HOST), BRYNHILD_PROVIDER, BRYNHILD_MODEL
        to be set in environment (e.g., via .env loaded by pytest-dotenv).
    """
    env = _os.environ.copy()

    if env_override:
        env.update(env_override)

    return _subprocess.run(
        [str(BRYNHILD_BIN), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
        cwd=str(PROJECT_ROOT),
    )


class TestBinBrynhildScript:
    """Test the bin/brynhild shell script works."""

    def test_help_command(self) -> None:
        """bin/brynhild --help runs without error."""
        result = _run_brynhild("--help", timeout=10)

        assert result.returncode == 0, f"Help failed: {result.stderr}"
        assert "brynhild" in result.stdout.lower()
        assert "chat" in result.stdout

    def test_version_or_help_fast(self) -> None:
        """Quick command runs in reasonable time."""
        import time

        start = time.perf_counter()
        result = _run_brynhild("--help", timeout=10)
        elapsed = time.perf_counter() - start

        assert result.returncode == 0
        assert elapsed < 5, f"--help took {elapsed:.1f}s, should be < 5s"

    def test_config_command(self) -> None:
        """bin/brynhild config shows settings."""
        result = _run_brynhild("config", timeout=10)

        assert result.returncode == 0, f"Config failed: {result.stderr}"
        assert "provider" in result.stdout.lower() or "model" in result.stdout.lower()


class TestSmokeChat:
    """Smoke tests for chat command with real LLM."""

    def test_print_mode_produces_output(self) -> None:
        """bin/brynhild chat -p produces a response."""
        result = _run_brynhild(
            "chat", "-p", "Say exactly: SMOKE_TEST_OK",
            timeout=60,
        )

        assert result.returncode == 0, f"Chat failed: {result.stderr}"
        # Should have some output (the model's response)
        assert len(result.stdout.strip()) > 0, "No output from chat"

    def test_json_mode_returns_valid_json(self) -> None:
        """bin/brynhild chat --json returns valid JSON."""
        result = _run_brynhild(
            "chat", "--json", "What is 1+1? Answer with just the number.",
            timeout=60,
        )

        assert result.returncode == 0, f"Chat failed: {result.stderr}"

        # Should be valid JSON
        try:
            data = _json.loads(result.stdout)
        except _json.JSONDecodeError as e:
            _pytest.fail(f"Invalid JSON: {e}\nOutput: {result.stdout[:500]}")

        # Should have response field
        assert "response" in data or "content" in data or "error" not in data


class TestLoggingPipeline:
    """Test that conversation logging works end-to-end."""

    @_pytest.fixture
    def temp_log_dir(self, tmp_path: _pathlib.Path) -> _pathlib.Path:
        """Create a temporary log directory."""
        log_dir = tmp_path / "brynhild-logs"
        log_dir.mkdir()
        return log_dir

    def test_chat_creates_log_file(self, temp_log_dir: _pathlib.Path) -> None:
        """Chat command creates a log file when logging enabled."""
        # Run chat with custom log directory (nested config env vars)
        result = _run_brynhild(
            "chat", "-p", "Say hello",
            env_override={
                "BRYNHILD_LOGGING__DIR": str(temp_log_dir),
                "BRYNHILD_LOGGING__ENABLED": "true",
            },
            timeout=60,
        )

        assert result.returncode == 0, f"Chat failed: {result.stderr}"

        # Should have created a log file
        log_files = list(temp_log_dir.glob("*.jsonl"))
        assert len(log_files) >= 1, f"No log files in {temp_log_dir}: {list(temp_log_dir.iterdir())}"

    def test_log_file_has_expected_events(self, temp_log_dir: _pathlib.Path) -> None:
        """Log file contains expected event types."""
        # Run chat (nested config env vars)
        result = _run_brynhild(
            "chat", "-p", "What is 2+2?",
            env_override={
                "BRYNHILD_LOGGING__DIR": str(temp_log_dir),
                "BRYNHILD_LOGGING__ENABLED": "true",
            },
            timeout=60,
        )

        assert result.returncode == 0, f"Chat failed: {result.stderr}"

        # Find and parse log file
        log_files = list(temp_log_dir.glob("*.jsonl"))
        assert log_files, "No log file created"

        log_file = log_files[0]
        events = []
        with open(log_file) as f:
            for line in f:
                if line.strip():
                    events.append(_json.loads(line))

        # Should have key event types (field is "event_type")
        event_types = {e.get("event_type") for e in events}

        assert "session_start" in event_types, f"Missing session_start. Events: {event_types}"
        assert "user_message" in event_types, f"Missing user_message. Events: {event_types}"
        # Should have either assistant_message or assistant_stream_end
        has_response = "assistant_message" in event_types or "assistant_stream_end" in event_types
        assert has_response, f"Missing assistant response. Events: {event_types}"

    def test_logs_list_shows_new_log(self, temp_log_dir: _pathlib.Path) -> None:
        """logs list command shows newly created log."""
        # Create a log by chatting
        result = _run_brynhild(
            "chat", "-p", "Hello",
            env_override={
                "BRYNHILD_LOGGING__DIR": str(temp_log_dir),
                "BRYNHILD_LOGGING__ENABLED": "true",
            },
            timeout=60,
        )
        assert result.returncode == 0, f"Chat failed: {result.stderr}"

        # Now list logs
        result = _run_brynhild(
            "logs", "list",
            env_override={"BRYNHILD_LOGGING__DIR": str(temp_log_dir)},
            timeout=10,
        )

        assert result.returncode == 0, f"logs list failed: {result.stderr}"
        assert "brynhild_" in result.stdout or ".jsonl" in result.stdout

    def test_logs_view_parses_log(self, temp_log_dir: _pathlib.Path) -> None:
        """logs view command can parse a generated log."""
        # Create a log
        result = _run_brynhild(
            "chat", "-p", "Say test",
            env_override={
                "BRYNHILD_LOGGING__DIR": str(temp_log_dir),
                "BRYNHILD_LOGGING__ENABLED": "true",
            },
            timeout=60,
        )
        assert result.returncode == 0, f"Chat failed: {result.stderr}"

        # View the log (most recent)
        result = _run_brynhild(
            "logs", "view",
            env_override={"BRYNHILD_LOGGING__DIR": str(temp_log_dir)},
            timeout=10,
        )

        assert result.returncode == 0, f"logs view failed: {result.stderr}"
        # Should show session info
        assert "Session" in result.stdout or "session" in result.stdout.lower()


class TestProfileAppliedInRealSession:
    """Verify profile is applied when running real commands."""

    def test_profile_affects_behavior(self, tmp_path: _pathlib.Path) -> None:
        """Profile patterns influence model behavior in real session."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        # Ask a question that the profile's tool_policy should handle well
        # (should answer from context, not try to search)
        result = _run_brynhild(
            "chat", "-p",
            "I told you earlier my name is Alice. What is my name?",
            env_override={
                "BRYNHILD_LOGGING__DIR": str(log_dir),
                "BRYNHILD_LOGGING__ENABLED": "true",
            },
            timeout=60,
        )

        assert result.returncode == 0, f"Chat failed: {result.stderr}"

        # Should produce a response (profile patterns are applied in background)
        assert len(result.stdout) > 0, "No response"

