"""
Settings configuration using pydantic-settings.

Loads configuration from environment variables with BRYNHILD_ prefix.
"""

import getpass as _getpass
import pathlib as _pathlib
import subprocess as _subprocess
import typing as _typing

import pydantic as _pydantic
import pydantic_settings as _pydantic_settings


def _get_username() -> str:
    """Get the current username for directory naming."""
    try:
        return _getpass.getuser()
    except Exception:
        return "unknown"


class ProjectRootTooWideError(Exception):
    """Raised when project root would be an overly broad directory like ~ or /."""

    pass


def find_git_root(start_path: _pathlib.Path | None = None) -> _pathlib.Path | None:
    """Find the git repository root from the given path or current directory."""
    if start_path is None:
        start_path = _pathlib.Path.cwd()

    try:
        result = _subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            cwd=start_path,
            timeout=5,
        )
        if result.returncode == 0:
            return _pathlib.Path(result.stdout.strip())
    except (_subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _is_overly_wide_root(path: _pathlib.Path) -> bool:
    """Check if a path is too broad to be a safe project root."""
    resolved = path.resolve()
    home = _pathlib.Path.home().resolve()
    root = _pathlib.Path("/").resolve()

    # Exact matches to ~ or / are too wide
    if resolved in (home, root):
        return True

    # Also block common overly-broad locations
    dangerous_roots = [
        _pathlib.Path("/Users").resolve(),
        _pathlib.Path("/home").resolve(),
        _pathlib.Path("/var").resolve(),
        _pathlib.Path("/etc").resolve(),
        _pathlib.Path("/tmp").resolve(),
        _pathlib.Path("/private/tmp").resolve(),
    ]

    return resolved in dangerous_roots


def find_project_root(
    start_path: _pathlib.Path | None = None,
    *,
    allow_wide_root: bool = False,
) -> _pathlib.Path:
    """
    Find the project root directory.

    Tries (in order):
    1. Git repository root
    2. Directory containing pyproject.toml or setup.py
    3. Current working directory

    Args:
        start_path: Starting path for search. Defaults to cwd.
        allow_wide_root: If False, raises ProjectRootTooWideError if
            the detected root is ~ or /. Defaults to False.

    Raises:
        ProjectRootTooWideError: If root would be too broad and
            allow_wide_root is False.
    """
    if start_path is None:
        start_path = _pathlib.Path.cwd()

    result: _pathlib.Path | None = None

    # Try git root first
    git_root = find_git_root(start_path)
    if git_root:
        result = git_root
    else:
        # Walk up looking for project markers
        current = start_path.resolve()
        markers = ["pyproject.toml", "setup.py", "setup.cfg", ".git"]

        while current != current.parent:
            for marker in markers:
                if (current / marker).exists():
                    result = current
                    break
            if result:
                break
            current = current.parent

    # Fall back to current directory if nothing found
    if result is None:
        result = _pathlib.Path.cwd()

    # Safety check: reject overly broad roots
    if not allow_wide_root and _is_overly_wide_root(result):
        raise ProjectRootTooWideError(
            f"Project root '{result}' is too broad for safe operation.\n"
            f"Navigate to a specific project directory, or set "
            f"BRYNHILD_ALLOW_HOME_DIRECTORY=true to override."
        )

    return result


class Settings(_pydantic_settings.BaseSettings):
    """
    Brynhild configuration settings.

    All settings can be overridden via environment variables with BRYNHILD_ prefix.
    Example: BRYNHILD_PROVIDER=openrouter
    """

    model_config = _pydantic_settings.SettingsConfigDict(
        env_prefix="BRYNHILD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def construct_without_dotenv(cls, **kwargs: _typing.Any) -> "Settings":
        """Create Settings from environment variables only, without loading .env file.

        Useful for:
        - Test isolation (prevent .env from polluting tests)
        - CI/CD environments (pure env var config)
        - Debugging (reproduce issues without .env interference)
        """
        return cls(_env_file=None, **kwargs)  # type: ignore[call-arg]

    # Provider settings
    provider: str = _pydantic.Field(
        default="openrouter",
        description="LLM provider to use. Built-in: openrouter, ollama. Plugins can add more.",
    )

    model: str = _pydantic.Field(
        default="openai/gpt-oss-120b",
        description="Model to use for completions (OpenRouter format)",
    )

    # API Keys (loaded from env without BRYNHILD_ prefix for compatibility)
    openrouter_api_key: str | None = _pydantic.Field(
        default=None,
        description="OpenRouter API key",
        validation_alias="OPENROUTER_API_KEY",
    )

    # Output settings
    output_format: _typing.Literal["text", "json", "stream"] = _pydantic.Field(
        default="text",
        description="Output format for non-interactive mode",
    )

    # Behavior settings
    max_tokens: int = _pydantic.Field(
        default=8192,
        ge=1,
        le=200000,
        description="Maximum tokens for completions",
    )

    verbose: bool = _pydantic.Field(
        default=False,
        description="Enable verbose output",
    )

    # Reasoning format for conversation history
    reasoning_format: _typing.Literal["reasoning_field", "thinking_tags", "none", "auto"] = _pydantic.Field(
        default="auto",
        description=(
            "How to include model reasoning in conversation history. "
            "'reasoning_field': separate field (OpenRouter convention), "
            "'thinking_tags': wrap in <thinking> tags in content, "
            "'none': don't include reasoning, "
            "'auto': use provider's default"
        ),
    )

    # Permission settings
    dangerously_skip_permissions: bool = _pydantic.Field(
        default=False,
        description="Skip all permission checks (dangerous!)",
    )

    # Sandbox settings
    sandbox_enabled: bool = _pydantic.Field(
        default=True,
        description="Enable sandbox restrictions for tool execution",
    )

    sandbox_allow_network: bool = _pydantic.Field(
        default=False,
        description="Allow network access in sandboxed commands",
    )

    dangerously_skip_sandbox: bool = _pydantic.Field(
        default=False,
        description="Skip OS-level sandbox (DANGEROUS - for testing only)",
    )

    allowed_paths: str = _pydantic.Field(
        default="",
        description="Additional paths where writes are allowed (comma-separated)",
    )

    allow_home_directory: bool = _pydantic.Field(
        default=False,
        description="Allow running from overly broad directories like ~ or /",
    )

    # Logging settings
    log_conversations: bool = _pydantic.Field(
        default=True,
        description="Enable conversation logging to JSONL files",
    )

    log_dir: str = _pydantic.Field(
        default="",  # Empty = use config_dir/logs (computed at runtime)
        description="Directory for conversation log files (default: ~/.brynhild-{user}/logs)",
    )

    log_file: str | None = _pydantic.Field(
        default=None,
        description="Explicit log file path (overrides log_dir + auto filename)",
    )

    log_dir_private: bool = _pydantic.Field(
        default=True,
        description="Lock down log directory to owner-only (drwx------). Set False for shared access.",
    )

    # Tool settings
    disable_builtin_tools: bool = _pydantic.Field(
        default=False,
        description="Disable all builtin tools (use only plugin tools)",
    )

    disabled_tools: str = _pydantic.Field(
        default="",
        description="Comma-separated list of tool names to disable (e.g., 'Bash,Write')",
    )

    # Directory settings (computed at runtime)
    @property
    def config_dir(self) -> _pathlib.Path:
        """User configuration directory (~/.brynhild/)."""
        return _pathlib.Path.home() / ".brynhild"

    @property
    def project_root(self) -> _pathlib.Path:
        """Project root directory (git root or cwd)."""
        return find_project_root(allow_wide_root=self.allow_home_directory)

    @property
    def sessions_dir(self) -> _pathlib.Path:
        """Directory for session storage."""
        return self.config_dir / "sessions"

    @property
    def logs_dir(self) -> _pathlib.Path:
        """Directory for conversation log files.

        Default: /tmp/brynhild-logs-{username}
        The username suffix prevents accidental log sharing in multi-user systems.
        """
        if self.log_dir:
            return _pathlib.Path(self.log_dir)
        username = _get_username()
        return _pathlib.Path(f"/tmp/brynhild-logs-{username}")

    def get_api_key(self) -> str | None:
        """Get the API key for the configured provider."""
        if self.provider == "openrouter":
            return self.openrouter_api_key
        return None

    def get_allowed_paths(self) -> list[_pathlib.Path]:
        """Get additional allowed paths as Path objects."""
        import os as _os

        if not self.allowed_paths or not self.allowed_paths.strip():
            return []

        paths = []
        for p in self.allowed_paths.split(","):
            p = p.strip()
            if p:
                # Expand ~ and resolve
                expanded = _os.path.expanduser(p)
                paths.append(_pathlib.Path(expanded).resolve())
        return paths

    def get_disabled_tools(self) -> set[str]:
        """Get set of disabled tool names."""
        if not self.disabled_tools or not self.disabled_tools.strip():
            return set()

        return {name.strip() for name in self.disabled_tools.split(",") if name.strip()}

    def is_tool_disabled(self, tool_name: str) -> bool:
        """Check if a specific tool is disabled."""
        if self.disable_builtin_tools:
            return True
        return tool_name in self.get_disabled_tools()

    def to_dict(self) -> dict[str, _typing.Any]:
        """Convert settings to dictionary (for JSON output)."""
        return {
            "provider": self.provider,
            "model": self.model,
            "output_format": self.output_format,
            "max_tokens": self.max_tokens,
            "verbose": self.verbose,
            "has_api_key": self.get_api_key() is not None,
            "config_dir": str(self.config_dir),
            "project_root": str(self.project_root),
            "sessions_dir": str(self.sessions_dir),
            "sandbox_enabled": self.sandbox_enabled,
            "sandbox_allow_network": self.sandbox_allow_network,
            "allowed_paths": [str(p) for p in self.get_allowed_paths()],
            "allow_home_directory": self.allow_home_directory,
            "log_conversations": self.log_conversations,
            "log_dir": str(self.logs_dir),
            "log_dir_private": self.log_dir_private,
            "log_file": self.log_file,
            "disable_builtin_tools": self.disable_builtin_tools,
            "disabled_tools": list(self.get_disabled_tools()),
        }
