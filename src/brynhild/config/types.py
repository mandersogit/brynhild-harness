"""Configuration type definitions for Brynhild settings.

This module defines the Pydantic models used to represent configuration
structures. These are "config section" types that will be nested within
the main Settings class.

Phase 2 types (basic sections):
- BehaviorConfig: max_tokens, verbose, show_thinking, etc.
- SandboxConfig: enabled, allow_network, allowed_paths
- LoggingConfig: enabled, dir, private, raw_payloads
- SessionConfig: auto_save, history_limit
- ProviderInstanceConfig: enabled, base_url, cache_ttl
- ProvidersConfig: default, dynamic provider instances
- PluginConfig: enabled, timeout
- PluginsConfig: search_paths, enabled dict, dynamic plugins
- ToolConfig: require_approval, allowed_commands, etc.
- ToolsConfig: disabled dict, dynamic tools

Phase 4 types (model identity - to be added):
- ModelDescriptor
- ProviderBinding
- ModelIdentity
- ModelsConfig

Design decision: All types use `extra="allow"` to preserve unknown fields.
This enables strict validation mode where users can audit their config for
typos and unknown keys. Use `get_extra_fields()` to inspect unknown fields.
"""

import typing as _typing

import pydantic as _pydantic


# =============================================================================
# Base class with introspection
# =============================================================================


class ConfigBase(_pydantic.BaseModel):
    """
    Base class for all config types.
    
    Provides introspection for strict validation mode.
    All config types use `extra="allow"` so unknown fields are preserved
    rather than silently dropped. This enables auditing for typos.
    """

    model_config = _pydantic.ConfigDict(extra="allow")

    def get_extra_fields(self) -> dict[str, _typing.Any]:
        """
        Return fields that were provided but not in the schema.
        
        Use this for strict validation / config auditing. Unknown fields
        may indicate typos or outdated config keys.
        
        Returns:
            Dict of field_name → value for all unrecognized fields.
        """
        return dict(self.model_extra) if self.model_extra else {}

    def has_extra_fields(self) -> bool:
        """Check if this config has any unrecognized fields."""
        return bool(self.model_extra)

    def collect_all_extra_fields(
        self,
        prefix: str = "",
    ) -> dict[str, _typing.Any]:
        """
        Recursively collect extra fields from this config and nested configs.
        
        Returns a flat dict with dotted paths as keys, e.g.:
            {"behavior.verboes": True, "instances.my-plugin.enbaled": True}
        
        Args:
            prefix: Dotted path prefix (used in recursion).
        
        Returns:
            Flat dict of path → value for all unrecognized fields.
        """
        result: dict[str, _typing.Any] = {}

        # Add our own extra fields
        for key, value in self.get_extra_fields().items():
            path = f"{prefix}.{key}" if prefix else key
            result[path] = value

        # Recurse into known fields that are ConfigBase or dict[str, ConfigBase]
        for field_name in self.__class__.model_fields:
            value = getattr(self, field_name, None)
            child_prefix = f"{prefix}.{field_name}" if prefix else field_name

            if isinstance(value, ConfigBase):
                # Direct ConfigBase child
                result.update(value.collect_all_extra_fields(child_prefix))
            elif isinstance(value, dict):
                # Dict of ConfigBase (e.g., instances: dict[str, ProviderInstanceConfig])
                for key, item in value.items():
                    if isinstance(item, ConfigBase):
                        item_prefix = f"{child_prefix}.{key}"
                        result.update(item.collect_all_extra_fields(item_prefix))

        return result


# =============================================================================
# Behavior Settings
# =============================================================================


class BehaviorConfig(ConfigBase):
    """
    General behavior settings.

    YAML section: behavior.*
    """

    max_tokens: int = _pydantic.Field(default=8192, ge=1, le=200000)
    """Maximum tokens for completions."""

    output_format: _typing.Literal["text", "json", "stream"] = "text"
    """Output format for non-interactive mode."""

    verbose: bool = False
    """Enable verbose output."""

    show_thinking: bool = False
    """Show model thinking/reasoning content."""

    show_cost: bool = False
    """Show cost information (OpenRouter only)."""

    reasoning_format: _typing.Literal[
        "reasoning_field", "thinking_tags", "none", "auto"
    ] = "auto"
    """How to include reasoning in conversation history."""


# =============================================================================
# Sandbox Settings
# =============================================================================


class SandboxConfig(ConfigBase):
    """
    Sandbox/security settings.

    YAML section: sandbox.*
    """

    enabled: bool = True
    """Enable sandbox restrictions."""

    allow_network: bool = False
    """Allow network access in sandbox."""

    allowed_paths: list[str] = _pydantic.Field(default_factory=list)
    """Additional paths where writes are allowed."""

    # Note: dangerously_skip_* are NOT in config - CLI only


# =============================================================================
# Logging Settings
# =============================================================================


class LoggingConfig(ConfigBase):
    """
    Logging settings.

    YAML section: logging.*
    """

    enabled: bool = True
    """Enable conversation logging."""

    dir: str | None = None
    """Log directory. None = use default."""

    level: _typing.Literal["debug", "info", "warning", "error"] = "info"
    """Log level."""

    private: bool = True
    """Lock log directory to owner-only (drwx------)."""

    raw_payloads: bool = False
    """Log full request/response JSON."""


# =============================================================================
# Session Settings
# =============================================================================


class SessionConfig(ConfigBase):
    """
    Session settings.

    YAML section: session.*
    """

    auto_save: bool = True
    """Automatically save sessions."""

    history_limit: int = _pydantic.Field(default=100, ge=1)
    """Maximum sessions to retain."""


# =============================================================================
# Models Settings
# =============================================================================


class ModelsConfig(ConfigBase):
    """
    Model-related configuration.

    YAML section: models.*

    Note: This is a minimal implementation for Phase 3.
    Phase 4 will add full ModelIdentity and registry support.
    """

    default: str = "anthropic/claude-sonnet-4"
    """Default model when not specified."""


# =============================================================================
# Provider Settings
# =============================================================================


class ProviderInstanceConfig(ConfigBase):
    """
    Configuration for a specific provider instance.

    YAML section: providers.<name>.*

    Keys:
        enabled: Whether provider is enabled (bool)
        base_url: Override base URL (str, optional)
        cache_ttl: Model cache TTL in seconds (int)
    """

    enabled: bool = True
    """Whether this provider is enabled."""

    base_url: str | None = None
    """Override base URL (for self-hosted providers)."""

    cache_ttl: int = _pydantic.Field(default=3600, ge=0)
    """Model list cache TTL in seconds."""


class ProvidersConfig(ConfigBase):
    """
    Provider-related configuration.

    YAML section: providers.*

    YAML shape (users write):
        providers:
          default: openrouter
          openrouter:
            enabled: true
            cache_ttl: 3600

    Internal shape (after pre-validator):
        providers:
          default: openrouter
          instances:
            openrouter: ProviderInstanceConfig(...)

    This transformation enables full validation of provider configs at load time.
    """

    default: str = "openrouter"
    """Default provider when not specified."""

    instances: dict[str, ProviderInstanceConfig] = _pydantic.Field(
        default_factory=dict
    )
    """Typed mapping of provider name -> config. Populated by pre-validator."""

    @_pydantic.model_validator(mode="before")
    @classmethod
    def _move_dynamic_to_instances(
        cls,
        values: dict[str, _typing.Any],
    ) -> dict[str, _typing.Any]:
        """Move dynamic provider keys into the typed instances dict."""
        if not isinstance(values, dict):
            return values

        reserved = {"default", "instances"}
        instances: dict[str, _typing.Any] = dict(values.pop("instances", {}) or {})

        # Move non-reserved keys to instances
        for key in list(values.keys()):
            if key not in reserved:
                instances[key] = values.pop(key)

        values["instances"] = instances
        return values

    def get_provider_config(self, name: str) -> ProviderInstanceConfig:
        """Get config for a specific provider."""
        if name in self.instances:
            return self.instances[name]
        return ProviderInstanceConfig()


# =============================================================================
# Plugin Settings
# =============================================================================


class PluginConfig(ConfigBase):
    """
    Configuration for a single plugin.

    YAML section: plugins.<name>.*

    Keys:
        enabled: Whether plugin is enabled (bool)
        timeout: Operation timeout in seconds (int)
        <other>: Plugin-specific settings
    """

    enabled: bool = True
    """Whether this plugin is enabled."""

    timeout: int = _pydantic.Field(default=300, ge=1)
    """Plugin operation timeout in seconds."""


class PluginsConfig(ConfigBase):
    """
    Plugin-related configuration.

    YAML section: plugins.*

    YAML shape (users write):
        plugins:
          search_paths: [~/.brynhild/plugins]
          enabled:
            my-plugin: false
          my-plugin:
            timeout: 600

    Internal shape (after pre-validator):
        plugins:
          search_paths: [...]
          enabled: {...}
          instances:
            my-plugin: PluginConfig(...)

    This transformation enables full validation of plugin configs at load time.
    """

    search_paths: list[str] = _pydantic.Field(default_factory=list)
    """Additional plugin search paths."""

    enabled: dict[str, bool] = _pydantic.Field(default_factory=dict)
    """
    Quick enable/disable toggle per plugin.
    Key is plugin name, value is enabled state.
    """

    instances: dict[str, PluginConfig] = _pydantic.Field(default_factory=dict)
    """Typed mapping of plugin name -> config. Populated by pre-validator."""

    @_pydantic.model_validator(mode="before")
    @classmethod
    def _move_dynamic_to_instances(
        cls,
        values: dict[str, _typing.Any],
    ) -> dict[str, _typing.Any]:
        """Move dynamic plugin keys into the typed instances dict."""
        if not isinstance(values, dict):
            return values

        reserved = {"search_paths", "enabled", "instances"}
        instances: dict[str, _typing.Any] = dict(values.pop("instances", {}) or {})

        # Move non-reserved keys to instances
        for key in list(values.keys()):
            if key not in reserved:
                instances[key] = values.pop(key)

        values["instances"] = instances
        return values

    def get_plugin_config(self, name: str) -> PluginConfig:
        """Get config for a specific plugin."""
        if name in self.instances:
            return self.instances[name]
        return PluginConfig()

    def is_plugin_enabled(self, name: str) -> bool:
        """Check if a plugin is enabled."""
        # Check explicit enabled dict first
        if name in self.enabled:
            return self.enabled[name]
        # Check plugin-specific config
        plugin_config = self.get_plugin_config(name)
        return plugin_config.enabled


# =============================================================================
# Tool Settings
# =============================================================================


class ToolConfig(ConfigBase):
    """
    Configuration for a single tool.

    YAML section: tools.<name>.*

    Keys:
        require_approval: "always" | "once" | "never"
        allowed_commands: Whitelist patterns (list[str])
        blocked_commands: Blacklist patterns (list[str])
        allowed_paths: Allowed file paths (list[str])
    """

    require_approval: _typing.Literal["always", "once", "never"] = "once"
    """When to require user approval."""

    allowed_commands: list[str] = _pydantic.Field(default_factory=list)
    """Whitelist patterns (for command tools)."""

    blocked_commands: list[str] = _pydantic.Field(default_factory=list)
    """Blacklist patterns (for command tools)."""

    allowed_paths: list[str] = _pydantic.Field(default_factory=list)
    """Allowed paths (for file tools)."""


class ToolsConfig(ConfigBase):
    """
    Tool-related configuration.

    YAML section: tools.*

    YAML shape (users write):
        tools:
          disabled:
            dangerous-tool: true
          bash:
            require_approval: always
            blocked_commands: [rm -rf]

    Internal shape (after pre-validator):
        tools:
          disabled: {...}
          instances:
            bash: ToolConfig(...)

    This transformation enables full validation of tool configs at load time.
    """

    disabled: dict[str, bool] = _pydantic.Field(default_factory=dict)
    """
    Tools to disable entirely.
    Dict for DCM mergeability. Key is tool name, value is whether disabled.
    """

    instances: dict[str, ToolConfig] = _pydantic.Field(default_factory=dict)
    """Typed mapping of tool name -> config. Populated by pre-validator."""

    @_pydantic.model_validator(mode="before")
    @classmethod
    def _move_dynamic_to_instances(
        cls,
        values: dict[str, _typing.Any],
    ) -> dict[str, _typing.Any]:
        """Move dynamic tool keys into the typed instances dict."""
        if not isinstance(values, dict):
            return values

        reserved = {"disabled", "instances"}
        instances: dict[str, _typing.Any] = dict(values.pop("instances", {}) or {})

        # Move non-reserved keys to instances
        for key in list(values.keys()):
            if key not in reserved:
                instances[key] = values.pop(key)

        values["instances"] = instances
        return values

    def get_tool_config(self, name: str) -> ToolConfig:
        """Get config for a specific tool."""
        if name in self.instances:
            return self.instances[name]
        return ToolConfig()

    def is_tool_disabled(self, name: str) -> bool:
        """Check if a tool is disabled."""
        return self.disabled.get(name, False)
