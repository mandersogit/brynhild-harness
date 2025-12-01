"""
Bash tool for executing shell commands.

This is the primary tool for interacting with the system.
Supports timeouts, background execution, and sandboxing via macOS sandbox-exec.
"""

from __future__ import annotations

import asyncio as _asyncio
import os as _os
import pathlib as _pathlib
import typing as _typing

import brynhild.constants as _constants
import brynhild.tools.base as base
import brynhild.tools.sandbox as sandbox


class BashTool(base.Tool):
    """
    Execute bash commands.

    Features:
    - Command execution with configurable timeout
    - Working directory management
    - Sandbox mode via macOS sandbox-exec
    - Dry-run mode for testing
    """

    def __init__(
        self,
        working_dir: _pathlib.Path | None = None,
        timeout_ms: int = _constants.DEFAULT_BASH_TIMEOUT_MS,
        sandbox_enabled: bool = True,
        dry_run: bool = False,
    ) -> None:
        """
        Initialize the Bash tool.

        Args:
            working_dir: Working directory for commands (default: cwd)
            timeout_ms: Default timeout in milliseconds
            sandbox_enabled: Whether to wrap commands in sandbox-exec
            dry_run: If True, don't execute commands, just show what would run
        """
        self._working_dir = working_dir or _pathlib.Path.cwd()
        self._default_timeout_ms = timeout_ms
        self._sandbox_enabled = sandbox_enabled
        self._dry_run = dry_run
        self._sandbox_config: sandbox.SandboxConfig | None = None

    @property
    def name(self) -> str:
        return "Bash"

    @property
    def description(self) -> str:
        return (
            "Execute a bash command. Use this for running shell commands, "
            "scripts, or interacting with the system. Commands run in the "
            "project directory by default."
        )

    def get_input_schema(self) -> dict[str, _typing.Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": f"Timeout in milliseconds (default: {_constants.DEFAULT_BASH_TIMEOUT_MS})",
                },
            },
            "required": ["command"],
        }

    @property
    def working_dir(self) -> _pathlib.Path:
        """Get the current working directory."""
        return self._working_dir

    @working_dir.setter
    def working_dir(self, path: _pathlib.Path) -> None:
        """Set the working directory."""
        self._working_dir = path
        # Update sandbox config when working dir changes
        if self._sandbox_config:
            self._sandbox_config = sandbox.SandboxConfig(
                project_root=path,
                dry_run=self._dry_run,
            )

    def configure_sandbox(
        self,
        project_root: _pathlib.Path | None = None,
        allowed_paths: list[_pathlib.Path] | None = None,
        allow_network: bool = False,
    ) -> None:
        """
        Configure sandbox settings.

        Args:
            project_root: Root directory for write access
            allowed_paths: Additional paths where writes are allowed
            allow_network: Whether to allow network access
        """
        self._sandbox_config = sandbox.SandboxConfig(
            project_root=project_root or self._working_dir,
            allowed_paths=allowed_paths,
            allow_network=allow_network,
            dry_run=self._dry_run,
        )

    def _get_sandbox_config(self) -> sandbox.SandboxConfig:
        """Get or create the sandbox configuration."""
        if self._sandbox_config is None:
            self._sandbox_config = sandbox.SandboxConfig(
                project_root=self._working_dir,
                dry_run=self._dry_run,
            )
        return self._sandbox_config

    async def execute(self, input: dict[str, _typing.Any]) -> base.ToolResult:
        """
        Execute a bash command.

        Args:
            input: Dict with 'command' (required) and 'timeout' (optional)

        Returns:
            ToolResult with stdout/stderr and success status
        """
        command = input.get("command", "")
        if not command:
            return base.ToolResult(
                success=False,
                output="",
                error="No command provided",
            )

        timeout_ms = input.get("timeout", self._default_timeout_ms)
        timeout_sec = timeout_ms / 1000.0

        # Handle dry-run mode
        if self._dry_run:
            return base.ToolResult(
                success=True,
                output=f"[DRY RUN] Would execute: {command}",
                error=None,
            )

        # Prepare command (with or without sandbox)
        profile_path: _pathlib.Path | None = None
        actual_command = command

        if self._sandbox_enabled:
            config = self._get_sandbox_config()
            actual_command, profile_path = sandbox.get_sandbox_command(command, config)

        try:
            # Create subprocess
            proc = await _asyncio.create_subprocess_shell(
                actual_command,
                stdout=_asyncio.subprocess.PIPE,
                stderr=_asyncio.subprocess.PIPE,
                cwd=str(self._working_dir),
                env=self._get_env(),
            )

            # Wait for completion with timeout
            try:
                stdout, stderr = await _asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout_sec,
                )
            except TimeoutError:
                # Kill the process on timeout
                proc.kill()
                await proc.wait()
                return base.ToolResult(
                    success=False,
                    output="",
                    error=f"Command timed out after {timeout_ms}ms",
                )

            # Decode output
            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            # Combine output (stdout first, then stderr if present)
            output = stdout_str
            if stderr_str:
                if output:
                    output += "\n--- stderr ---\n"
                output += stderr_str

            # Check for sandbox violations in stderr
            error_msg = None
            if proc.returncode != 0:
                if "deny" in stderr_str.lower() or "sandbox" in stderr_str.lower():
                    error_msg = f"Sandbox blocked operation: {stderr_str.rstrip()}"
                elif stderr_str:
                    error_msg = stderr_str.rstrip()

            return base.ToolResult(
                success=proc.returncode == 0,
                output=output.rstrip(),
                error=error_msg,
            )

        except FileNotFoundError:
            return base.ToolResult(
                success=False,
                output="",
                error=f"Working directory not found: {self._working_dir}",
            )
        except PermissionError as e:
            return base.ToolResult(
                success=False,
                output="",
                error=f"Permission denied: {e}",
            )
        except Exception as e:
            return base.ToolResult(
                success=False,
                output="",
                error=f"Failed to execute command: {e}",
            )
        finally:
            # Clean up sandbox profile
            if profile_path:
                sandbox.cleanup_sandbox_profile(profile_path)

    # Environment variables that are safe to pass to subprocesses
    _ENV_ALLOWLIST: set[str] = {
        # Basic shell functionality
        "PATH",
        "HOME",
        "USER",
        "SHELL",
        "TERM",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TZ",
        # Editor
        "EDITOR",
        "VISUAL",
        # Temp directories
        "TMPDIR",
        "TEMP",
        "TMP",
        # Python
        "PYTHONPATH",
        "PYTHONDONTWRITEBYTECODE",
        "VIRTUAL_ENV",
        # Git (non-credential)
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
        # XDG
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_CACHE_HOME",
    }

    # Patterns for environment variables that should NEVER be passed
    _ENV_BLOCKLIST_PATTERNS: tuple[str, ...] = (
        # API keys and tokens
        "_API_KEY",
        "_SECRET",
        "_TOKEN",
        "_PASSWORD",
        "_CREDENTIAL",
        "_AUTH",
        # Cloud providers
        "AWS_",
        "AZURE_",
        "GCP_",
        "GOOGLE_",
        "OPENAI_",
        "ANTHROPIC_",
        "OPENROUTER_",
        # Other sensitive
        "GITHUB_TOKEN",
        "GITLAB_TOKEN",
        "NPM_TOKEN",
        "PYPI_TOKEN",
        "DOCKER_",
        "KUBECONFIG",
    )

    def _get_env(self) -> dict[str, str]:
        """
        Get environment variables for subprocess.

        Returns a filtered environment with sensitive variables removed.
        Only variables in the allowlist are passed, and any matching
        blocklist patterns are explicitly excluded.
        """
        env: dict[str, str] = {}

        for key, value in _os.environ.items():
            # Check blocklist patterns first (higher priority)
            is_blocked = any(
                pattern in key.upper() for pattern in self._ENV_BLOCKLIST_PATTERNS
            )
            if is_blocked:
                continue

            # Check allowlist
            if key in self._ENV_ALLOWLIST:
                env[key] = value

        return env
