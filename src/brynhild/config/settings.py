"""
Settings configuration using pydantic-settings.

Loads configuration from:
1. Constructor arguments (highest precedence)
2. Environment variables with BRYNHILD_ prefix
3. .env file (if present)
4. Layered YAML config files via DeepChainMap:
   - Project config: .brynhild/config.yaml (highest)
   - User config: ~/.config/brynhild/config.yaml
   - Built-in defaults: bundled defaults/config.yaml (lowest)

Nested config uses double underscore delimiter:
  BRYNHILD_BEHAVIOR__MAX_TOKENS=16384
  BRYNHILD_SANDBOX__ENABLED=false
"""

import getpass as _getpass
import os as _os
import pathlib as _pathlib
import subprocess as _subprocess
import typing as _typing

import pydantic as _pydantic
import pydantic_settings as _pydantic_settings

import brynhild.config.sources as sources
import brynhild.config.types as types


def _get_env_file() -> str | None:
    """Determine which .env file to load.

    Priority:
    1. BRYNHILD_ENV_FILE if set (explicit override)
    2. .env in BRYNHILD_PROJECT_ROOT if set (brynhild's install directory)
    3. None (no .env loaded, rely on environment variables)

    This allows:
    - Users to override with BRYNHILD_ENV_FILE for custom setups
    - bin/brynhild to set BRYNHILD_PROJECT_ROOT so brynhild finds its own .env
    - Running without any .env if neither is set (pure env var config)
    """
    # Explicit override takes priority
    if env_file := _os.environ.get("BRYNHILD_ENV_FILE"):
        if _pathlib.Path(env_file).exists():
            return env_file
        # If explicitly set but doesn't exist, don't fall back silently
        return None

    # brynhild project's .env (set by bin/brynhild wrapper)
    if project_root := _os.environ.get("BRYNHILD_PROJECT_ROOT"):
        env_path = _pathlib.Path(project_root) / ".env"
        if env_path.exists():
            return str(env_path)

    # No .env found - rely on environment variables
    return None


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
    For nested config, use double underscore: BRYNHILD_BEHAVIOR__MAX_TOKENS=16384

    Config precedence (highest to lowest):
    1. Constructor arguments
    2. Environment variables (BRYNHILD_*)
    3. .env file
    4. Project config (.brynhild/config.yaml)
    5. User config (~/.config/brynhild/config.yaml)
    6. Built-in defaults
    """

    model_config = _pydantic_settings.SettingsConfigDict(
        env_prefix="BRYNHILD_",
        env_file=_get_env_file(),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",  # BRYNHILD_BEHAVIOR__MAX_TOKENS
        extra="allow",  # Preserve unknown fields for strict validation mode
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[_pydantic_settings.BaseSettings],
        init_settings: _pydantic_settings.PydanticBaseSettingsSource,
        env_settings: _pydantic_settings.PydanticBaseSettingsSource,
        dotenv_settings: _pydantic_settings.PydanticBaseSettingsSource,
        file_secret_settings: _pydantic_settings.PydanticBaseSettingsSource,
    ) -> tuple[_pydantic_settings.PydanticBaseSettingsSource, ...]:
        """
        Configure settings sources with precedence:
        1. init_settings (constructor args) — highest
        2. env_settings (BRYNHILD_* env vars)
        3. dotenv_settings (.env file)
        4. yaml_settings (config.yaml via DCM)
        5. (defaults via Field definitions) — lowest
        """
        # Get project_root for project-level config
        project_root = find_project_root(allow_wide_root=True)

        return (
            init_settings,
            env_settings,
            dotenv_settings,
            sources.DeepChainMapSettingsSource(settings_cls, project_root),
            file_secret_settings,
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

    @_pydantic.model_validator(mode="after")
    def _check_legacy_env_vars(self) -> "Settings":
        """
        Detect legacy flat environment variables and emit migration error.

        Per Q2 decision: hard break with detection. Old flat env vars like
        BRYNHILD_MODEL are no longer supported. Users must migrate to nested
        syntax: BRYNHILD_MODELS__DEFAULT.

        Set BRYNHILD_SKIP_MIGRATION_CHECK=1 to bypass (for tests during migration).
        """
        # Allow bypassing for tests/migration
        if _os.environ.get("BRYNHILD_SKIP_MIGRATION_CHECK"):
            return self

        # Map of legacy -> new env var names
        legacy_mappings = {
            "BRYNHILD_MODEL": "BRYNHILD_MODELS__DEFAULT",
            "BRYNHILD_PROVIDER": "BRYNHILD_PROVIDERS__DEFAULT",
            "BRYNHILD_VERBOSE": "BRYNHILD_BEHAVIOR__VERBOSE",
            "BRYNHILD_MAX_TOKENS": "BRYNHILD_BEHAVIOR__MAX_TOKENS",
            "BRYNHILD_OUTPUT_FORMAT": "BRYNHILD_BEHAVIOR__OUTPUT_FORMAT",
            "BRYNHILD_SANDBOX_ENABLED": "BRYNHILD_SANDBOX__ENABLED",
            "BRYNHILD_SANDBOX_ALLOW_NETWORK": "BRYNHILD_SANDBOX__ALLOW_NETWORK",
            "BRYNHILD_LOG_CONVERSATIONS": "BRYNHILD_LOGGING__ENABLED",
            "BRYNHILD_LOG_DIR": "BRYNHILD_LOGGING__DIR",
            "BRYNHILD_LOG_DIR_PRIVATE": "BRYNHILD_LOGGING__PRIVATE",
            "BRYNHILD_RAW_LOG": "BRYNHILD_LOGGING__RAW_PAYLOADS",
            "BRYNHILD_DISABLED_TOOLS": "BRYNHILD_TOOLS__DISABLED (as dict)",
            "BRYNHILD_DISABLE_BUILTIN_TOOLS": "BRYNHILD_TOOLS__DISABLED__BUILTIN (as dict)",
        }

        # Check for legacy env vars
        detected = []
        for legacy, new in legacy_mappings.items():
            if _os.environ.get(legacy):
                detected.append(f"  {legacy} -> {new}")

        if detected:
            raise ValueError(
                "Legacy environment variables detected. Brynhild now uses nested "
                "config syntax.\n\n"
                "Please update the following environment variables:\n"
                + "\n".join(detected)
                + "\n\n"
                "For more information, see: https://brynhild.dev/docs/config-migration"
            )

        return self

    # =========================================================================
    # Config version (for future migrations)
    # =========================================================================

    version: int = _pydantic.Field(default=1, description="Config schema version")

    # =========================================================================
    # Nested config sections
    # =========================================================================

    models: types.ModelsConfig = _pydantic.Field(default_factory=types.ModelsConfig)
    """Model configuration (default model, registry in Phase 4)."""

    providers: types.ProvidersConfig = _pydantic.Field(
        default_factory=types.ProvidersConfig
    )
    """Provider configuration (default provider, per-provider settings)."""

    behavior: types.BehaviorConfig = _pydantic.Field(
        default_factory=types.BehaviorConfig
    )
    """Behavior settings (max_tokens, verbose, output_format, etc.)."""

    sandbox: types.SandboxConfig = _pydantic.Field(default_factory=types.SandboxConfig)
    """Sandbox/security settings."""

    logging: types.LoggingConfig = _pydantic.Field(default_factory=types.LoggingConfig)
    """Logging settings."""

    session: types.SessionConfig = _pydantic.Field(default_factory=types.SessionConfig)
    """Session settings."""

    plugins: types.PluginsConfig = _pydantic.Field(default_factory=types.PluginsConfig)
    """Plugin settings."""

    tools: types.ToolsConfig = _pydantic.Field(default_factory=types.ToolsConfig)
    """Tool settings."""

    # =========================================================================
    # Fields NOT in nested config (remain flat)
    # These are either:
    # - API keys (special env var handling)
    # - Dangerous flags (CLI only, never in config files)
    # - Runtime overrides (log_file)
    # =========================================================================

    # API Keys (loaded from env without BRYNHILD_ prefix for compatibility)
    openrouter_api_key: str | None = _pydantic.Field(
        default=None,
        description="OpenRouter API key",
        validation_alias="OPENROUTER_API_KEY",
    )

    # Permission settings (CLI only, dangerous)
    dangerously_skip_permissions: bool = _pydantic.Field(
        default=False,
        description="Skip all permission checks (dangerous!)",
    )

    dangerously_skip_sandbox: bool = _pydantic.Field(
        default=False,
        description="Skip OS-level sandbox (DANGEROUS - for testing only)",
    )

    # Runtime overrides
    allow_home_directory: bool = _pydantic.Field(
        default=False,
        description="Allow running from overly broad directories like ~ or /",
    )

    log_file: str | None = _pydantic.Field(
        default=None,
        description="Explicit log file path (overrides log_dir + auto filename)",
    )

    # =========================================================================
    # Backward compatibility: Property aliases to nested config
    # These allow existing code to use settings.model instead of settings.models.default
    # =========================================================================

    @property
    def model(self) -> str:
        """Default model (alias to models.default)."""
        return self.models.default

    @model.setter
    def model(self, value: str) -> None:
        """Set default model."""
        self.models.default = value

    @property
    def provider(self) -> str:
        """Default provider (alias to providers.default)."""
        return self.providers.default

    @provider.setter
    def provider(self, value: str) -> None:
        """Set default provider."""
        self.providers.default = value

    @property
    def max_tokens(self) -> int:
        """Max tokens (alias to behavior.max_tokens)."""
        return self.behavior.max_tokens

    @max_tokens.setter
    def max_tokens(self, value: int) -> None:
        """Set max tokens."""
        self.behavior.max_tokens = value

    @property
    def verbose(self) -> bool:
        """Verbose mode (alias to behavior.verbose)."""
        return self.behavior.verbose

    @verbose.setter
    def verbose(self, value: bool) -> None:
        """Set verbose mode."""
        self.behavior.verbose = value

    @property
    def output_format(self) -> _typing.Literal["text", "json", "stream"]:
        """Output format (alias to behavior.output_format)."""
        return self.behavior.output_format

    @output_format.setter
    def output_format(self, value: _typing.Literal["text", "json", "stream"]) -> None:
        """Set output format."""
        self.behavior.output_format = value

    @property
    def reasoning_format(
        self,
    ) -> _typing.Literal["reasoning_field", "thinking_tags", "none", "auto"]:
        """Reasoning format (alias to behavior.reasoning_format)."""
        return self.behavior.reasoning_format

    @reasoning_format.setter
    def reasoning_format(
        self, value: _typing.Literal["reasoning_field", "thinking_tags", "none", "auto"]
    ) -> None:
        """Set reasoning format."""
        self.behavior.reasoning_format = value

    @property
    def reasoning_level(self) -> str:
        """Reasoning level (alias to behavior.reasoning_level)."""
        return self.behavior.reasoning_level

    @reasoning_level.setter
    def reasoning_level(self, value: str) -> None:
        """Set reasoning level."""
        self.behavior.reasoning_level = value

    @property
    def sandbox_enabled(self) -> bool:
        """Sandbox enabled (alias to sandbox.enabled)."""
        return self.sandbox.enabled

    @sandbox_enabled.setter
    def sandbox_enabled(self, value: bool) -> None:
        """Set sandbox enabled."""
        self.sandbox.enabled = value

    @property
    def sandbox_allow_network(self) -> bool:
        """Sandbox allow network (alias to sandbox.allow_network)."""
        return self.sandbox.allow_network

    @sandbox_allow_network.setter
    def sandbox_allow_network(self, value: bool) -> None:
        """Set sandbox allow network."""
        self.sandbox.allow_network = value

    @property
    def allowed_paths(self) -> str:
        """Allowed paths as comma-separated string (for CLI compat)."""
        return ",".join(self.sandbox.allowed_paths)

    @allowed_paths.setter
    def allowed_paths(self, value: str) -> None:
        """Set allowed paths from comma-separated string."""
        if value and value.strip():
            self.sandbox.allowed_paths = [p.strip() for p in value.split(",") if p.strip()]
        else:
            self.sandbox.allowed_paths = []

    @property
    def log_conversations(self) -> bool:
        """Log conversations enabled (alias to logging.enabled)."""
        return self.logging.enabled

    @log_conversations.setter
    def log_conversations(self, value: bool) -> None:
        """Set log conversations."""
        self.logging.enabled = value

    @property
    def log_dir(self) -> str:
        """Log directory (alias to logging.dir, with default handling)."""
        return self.logging.dir or ""

    @log_dir.setter
    def log_dir(self, value: str) -> None:
        """Set log directory."""
        self.logging.dir = value if value else None

    @property
    def log_dir_private(self) -> bool:
        """Log dir private mode (alias to logging.private)."""
        return self.logging.private

    @log_dir_private.setter
    def log_dir_private(self, value: bool) -> None:
        """Set log dir private."""
        self.logging.private = value

    @property
    def raw_log(self) -> bool:
        """Raw payload logging (alias to logging.raw_payloads)."""
        return self.logging.raw_payloads

    @raw_log.setter
    def raw_log(self, value: bool) -> None:
        """Set raw log."""
        self.logging.raw_payloads = value

    @property
    def disable_builtin_tools(self) -> bool:
        """Check if builtin tools disabled (computed from tools.disabled)."""
        # This was a flat bool before; now we check for a special marker
        return self.tools.disabled.get("__builtin__", False)

    @property
    def disabled_tools(self) -> str:
        """Get disabled tools as comma-separated string (for CLI compat)."""
        return ",".join(k for k, v in self.tools.disabled.items() if v and k != "__builtin__")

    # =========================================================================
    # Directory settings (computed at runtime)
    # =========================================================================

    @property
    def config_dir(self) -> _pathlib.Path:
        """User configuration directory (~/.config/brynhild/)."""
        return sources.get_user_config_dir()

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
        if self.logging.dir:
            return _pathlib.Path(self.logging.dir)
        username = _get_username()
        return _pathlib.Path(f"/tmp/brynhild-logs-{username}")

    # =========================================================================
    # Helper methods
    # =========================================================================

    def get_api_key(self) -> str | None:
        """Get the API key for the configured provider."""
        if self.provider == "openrouter":
            return self.openrouter_api_key
        return None

    def get_allowed_paths(self) -> list[_pathlib.Path]:
        """Get additional allowed paths as Path objects."""
        paths = []
        for p in self.sandbox.allowed_paths:
            if p:
                # Expand ~ and resolve
                expanded = _os.path.expanduser(p)
                paths.append(_pathlib.Path(expanded).resolve())
        return paths

    def get_disabled_tools(self) -> set[str]:
        """Get set of disabled tool names."""
        return {
            name for name, disabled in self.tools.disabled.items()
            if disabled and name != "__builtin__"
        }

    def is_tool_disabled(self, tool_name: str) -> bool:
        """Check if a specific tool is disabled."""
        if self.disable_builtin_tools:
            return True
        return self.tools.is_tool_disabled(tool_name)

    # =========================================================================
    # Model Identity helpers (Phase 5)
    # =========================================================================

    def resolve_model_alias(self, name: str) -> str:
        """
        Resolve a model name to its canonical ID.

        If the name is an alias defined in models.aliases, returns the
        canonical model ID. Otherwise returns the name unchanged.

        Args:
            name: Model name or alias to resolve.

        Returns:
            Canonical model ID.
        """
        return self.models.aliases.get(name, name)

    def get_model_identity(self, canonical_id: str) -> types.ModelIdentity | None:
        """
        Get the ModelIdentity for a canonical model ID.

        Args:
            canonical_id: The canonical model identifier (e.g., "anthropic/claude-sonnet-4").

        Returns:
            ModelIdentity if found in registry, None otherwise.
        """
        return self.models.registry.get(canonical_id)

    def get_model_binding(
        self,
        canonical_id: str,
        provider: str | None = None,
    ) -> types.ProviderBinding | None:
        """
        Get the ProviderBinding for a model at a specific provider.

        Args:
            canonical_id: The canonical model identifier.
            provider: Provider name. Defaults to the configured default provider.

        Returns:
            ProviderBinding if found, None otherwise.
        """
        identity = self.get_model_identity(canonical_id)
        if identity is None:
            return None

        effective_provider = provider or self.providers.default
        return identity.get_binding(effective_provider)

    def get_native_model_id(
        self,
        canonical_id: str,
        provider: str | None = None,
    ) -> str | None:
        """
        Get the provider-native model ID for a canonical model.

        This is a convenience method that extracts just the model_id from
        the binding.

        Args:
            canonical_id: The canonical model identifier.
            provider: Provider name. Defaults to the configured default provider.

        Returns:
            Native model ID string if found, None otherwise.
        """
        binding = self.get_model_binding(canonical_id, provider)
        return binding.model_id if binding else None

    def get_effective_context(
        self,
        canonical_id: str,
        provider: str | None = None,
    ) -> int | None:
        """
        Get the effective context size for a model at a provider.

        Returns the provider-specific limit if set, otherwise falls back
        to the model's native context size from its descriptor.

        Args:
            canonical_id: The canonical model identifier.
            provider: Provider name. Defaults to the configured default provider.

        Returns:
            Effective context size in tokens, or None if unknown.
        """
        identity = self.get_model_identity(canonical_id)
        if identity is None:
            return None

        effective_provider = provider or self.providers.default
        return identity.effective_context(effective_provider)

    def get_favorites(self) -> list[str]:
        """
        Get list of favorite model canonical IDs.

        Returns models marked as favorites (value is True or a dict with
        truthy enabled status).

        Returns:
            List of canonical model IDs that are marked as favorites.
        """
        favorites = []
        for model_id, value in self.models.favorites.items():
            if isinstance(value, bool) and value or isinstance(value, dict) and value.get("enabled", True):
                favorites.append(model_id)
        return favorites

    # =========================================================================
    # Introspection (for strict validation mode)
    # =========================================================================

    def get_extra_fields(self) -> dict[str, _typing.Any]:
        """
        Get unknown fields at the top level of Settings.

        Use this for strict validation / config auditing.
        """
        return dict(self.model_extra) if self.model_extra else {}

    def collect_all_extra_fields(self) -> dict[str, _typing.Any]:
        """
        Recursively collect all extra fields from Settings and nested configs.

        Returns a flat dict with dotted paths as keys, e.g.:
            {"behavior.verboes": True, "providers.instances.openrouter.enabeld": True}

        Use this for strict validation / config auditing.
        """
        result: dict[str, _typing.Any] = {}

        # Top-level extra fields
        for key, value in self.get_extra_fields().items():
            result[key] = value

        # Recurse into nested config sections
        for field_name in ["models", "providers", "behavior", "sandbox",
                          "logging", "session", "plugins", "tools"]:
            nested = getattr(self, field_name, None)
            if nested is not None and hasattr(nested, "collect_all_extra_fields"):
                nested_extras = nested.collect_all_extra_fields(prefix=field_name)
                result.update(nested_extras)

        return result

    def has_extra_fields(self) -> bool:
        """Check if there are any unknown fields anywhere in the config."""
        return bool(self.collect_all_extra_fields())

    # =========================================================================
    # Serialization
    # =========================================================================

    def to_dict(self) -> dict[str, _typing.Any]:
        """Convert settings to dictionary (for JSON output)."""
        return {
            "version": self.version,
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
