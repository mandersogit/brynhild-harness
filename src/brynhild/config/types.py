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

Phase 4 types (model identity):
- ModelDescriptor: structured model attributes (family, size, architecture, etc.)
- ProviderBinding: provider-specific binding (model_id, max_context, alternatives)
- ModelIdentity: complete identity with bindings, descriptor, aliases

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
# Model Identity Types (Phase 4)
# =============================================================================


class ModelDescriptor(_pydantic.BaseModel):
    """
    Structured attributes of a model for deterministic matching.

    Used to match models across providers even when naming conventions differ.
    Example: Ollama "llama3.1:8b" → family="llama", series="3.1", size="8b"

    For MoE (Mixture of Experts) models:
    - size = total parameters (e.g., "235b" for qwen3-235b-a22b)
    - active_size = active parameters per forward pass (e.g., "22b")
    - architecture = "moe"

    Active size is crucial for estimating inference speed - a 235b MoE with
    22b active params runs closer to a 22b dense model than a 235b dense model.
    """

    model_config = _pydantic.ConfigDict(frozen=True)

    family: str
    """Model family: "llama", "qwen", "deepseek", "claude", "gpt", etc."""

    series: str | None = None
    """Version/series: "3.1", "2.5", "r1", "v3", "sonnet-4", etc."""

    size: str | None = None
    """
    Total parameter size: "7b", "8b", "70b", "235b", etc.
    For MoE models, this is the TOTAL parameter count.
    """

    active_size: str | None = None
    """
    Active parameters per forward pass (MoE models only).
    Examples:
      - "22b" for qwen3-235b-a22b (235b total, 22b active)
      - "3b" for ernie-4.5-21b-a3b-thinking (21b total, 3b active)
    None for dense models.
    """

    architecture: _typing.Literal["dense", "moe"] | None = None
    """
    Model architecture type.
    - "dense": Standard dense transformer (all params active)
    - "moe": Mixture of Experts (sparse activation)
    - None: Unknown/unspecified
    """

    context_size: int | None = None
    """
    Native maximum context window in tokens.

    This is the MODEL's native capability, not provider-specific limits.
    Examples:
      - 131072 for llama-3.1 (128K)
      - 200000 for claude-sonnet-4
      - 1048576 for gemini-2.5-pro (1M)

    Provider-specific limits are in ProviderBinding.max_context.
    """

    variant: str | None = None
    """Variant type: "instruct", "chat", "coder", "vl", "reasoner", "thinking", etc."""

    extra: dict[str, _typing.Any] = _pydantic.Field(default_factory=dict)
    """
    Additional attributes not covered by standard fields.
    Examples: quant="q4_K_M", multimodal=True, tool_use=True
    """

    @property
    def effective_size(self) -> str | None:
        """
        Return the size most relevant for performance estimation.
        For MoE: active_size. For dense: size.
        """
        if self.architecture == "moe" and self.active_size:
            return self.active_size
        return self.size


class ProviderBinding(_pydantic.BaseModel):
    """
    Binding of a canonical model ID to a specific provider's native ID.

    Contains provider-specific metadata that may differ from the model's
    native capabilities (e.g., context limits, pricing tiers).
    """

    model_config = _pydantic.ConfigDict(frozen=True)

    model_id: str
    """
    Provider-native model identifier.
    Examples:
      - OpenRouter: "meta-llama/llama-3.1-8b-instruct"
      - Ollama: "llama3.1:8b-instruct-q4_K_M"
      - HuggingFace: "meta-llama/Llama-3.1-8B-Instruct"
    """

    max_context: int | None = None
    """
    Provider-specific context limit (may be less than model's native limit).

    Some providers limit context below the model's capability.
    If None, assume model's native context_size applies.
    """

    pricing_tiers: dict[str, _typing.Any] | None = None
    """
    Provider-specific tiered pricing information.

    For providers with context-based pricing tiers (e.g., different rates
    above/below certain token thresholds).

    Example for Opus 4.5 with 200K tier:
      {"under_200k": {"input": 3.0, "output": 15.0},
       "over_200k": {"input": 6.0, "output": 30.0}}

    None if flat pricing or pricing not tracked.
    """

    alternatives: list[str] = _pydantic.Field(default_factory=list)
    """
    Alternative native IDs for this provider (e.g., different quants).

    The primary model_id is the "canonical" choice; alternatives are
    acceptable substitutes. Useful for Ollama where multiple quantizations
    map to the same logical model.

    Example: ["llama3.1:8b-instruct-q8_0", "llama3.1:8b-instruct-fp16"]
    """

    extra: dict[str, _typing.Any] = _pydantic.Field(default_factory=dict)
    """Additional provider-specific metadata."""


# Helper type for flexible binding specification in config files
BindingValue: _typing.TypeAlias = ProviderBinding | str
"""
In YAML config, bindings can be specified as:
  - Simple string: just the model_id (common case)
  - Full object: ProviderBinding with max_context, alternatives, etc.

Example YAML:
  bindings:
    openrouter: meta-llama/llama-3.1-8b-instruct     # Simple
    ollama:                                           # Rich
      model_id: llama3.1:8b-instruct-q4_K_M
      max_context: 65536
      alternatives:
        - llama3.1:8b-instruct-q8_0
"""


class ModelIdentity(_pydantic.BaseModel):
    """
    Complete identity for a model with all known provider bindings.

    The canonical_id is always OpenRouter-style (e.g., "meta-llama/llama-3.1-8b-instruct").
    This is the single source of truth for referring to a model across all providers.

    Key design decisions:
    - bindings use dicts (not lists) for DCM mergeability
    - aliases use dicts (not lists) for DCM mergeability
    - confidence indicates how this identity was established
    """

    model_config = _pydantic.ConfigDict(frozen=True)

    canonical_id: str
    """
    Always OR-style: "vendor/model-series-size-variant"
    Examples:
      - "meta-llama/llama-3.1-8b-instruct" (real OR model)
      - "anthropic/claude-sonnet-4" (real OR model)
      - "local/my-custom-model-7b" (synthetic for non-OR models)
    """

    bindings: dict[str, ProviderBinding | str] = _pydantic.Field(default_factory=dict)
    """
    Provider name → binding (ProviderBinding or simple model_id string).

    Dict structure for DCM mergeability: user can override one provider
    without replacing all bindings.

    Simple form (just model_id):
      {"openrouter": "meta-llama/llama-3.1-8b-instruct",
       "ollama": "llama3.1:8b-instruct-q4_K_M"}

    Rich form (with provider-specific metadata):
      {"ollama": ProviderBinding(
           model_id="llama3.1:8b-instruct-q4_K_M",
           max_context=65536,
           alternatives=["llama3.1:8b-instruct-q8_0"])}
    """

    descriptor: ModelDescriptor | None = None
    """Structured attributes for deterministic cross-provider matching."""

    aliases: dict[str, bool] = _pydantic.Field(default_factory=dict)
    """
    Alternative names that resolve to this model.

    Dict (not list) for DCM mergeability: user can add/remove aliases
    without replacing entire set.

    Example:
      {"llama3.1:8b": True,
       "llama-3.1-8b": True,
       "meta-llama/Llama-3.1-8B-Instruct": True,
       "old-alias": False}  # Disabled alias
    """

    confidence: _typing.Literal["curated", "matched", "synthetic"] = "curated"
    """
    How this identity was established:
    - "curated": Explicitly defined in registry (high confidence)
    - "matched": Algorithmically matched to OR model (medium confidence)
    - "synthetic": Generated for non-OR model (lower confidence)

    Helps distinguish authoritative mappings from runtime-discovered ones.
    """

    notes: str | None = None
    """Human-readable notes about this model identity."""

    # -------------------------------------------------------------------------
    # Helper methods
    # -------------------------------------------------------------------------

    def get_binding(self, provider: str) -> ProviderBinding | None:
        """Get binding for a provider, normalizing string to ProviderBinding."""
        value = self.bindings.get(provider)
        if value is None:
            return None
        if isinstance(value, str):
            return ProviderBinding(model_id=value)
        return value

    def get_native_id(self, provider: str) -> str | None:
        """Get native model ID for a provider (convenience method)."""
        binding = self.get_binding(provider)
        return binding.model_id if binding else None

    def effective_context(self, provider: str) -> int | None:
        """
        Get effective context size for a provider.

        Returns provider-specific max_context if set, otherwise
        falls back to model's native context_size from descriptor.
        """
        binding = self.get_binding(provider)
        if binding and binding.max_context is not None:
            return binding.max_context
        if self.descriptor:
            return self.descriptor.context_size
        return None


# =============================================================================
# Models Settings
# =============================================================================


class ModelsConfig(ConfigBase):
    """
    Model-related configuration.

    YAML section: models.*

    Architecture note:
        DeepChainMap is used ONLY for merging YAML layers at load time.
        After merging, Pydantic validates all data and stores typed objects.
        This means:
        - All validation errors surface at startup (fail-fast)
        - No raw dicts stored; everything is typed
        - DCM is a merge tool, not a storage layer
    """

    default: str = "openai/gpt-oss-120b"
    """Default model when not specified."""

    favorites: dict[str, bool | dict[str, _typing.Any]] = _pydantic.Field(
        default_factory=dict
    )
    """
    Models to show in shortlists (e.g., `brynhild models list`).

    Values can be:
    - True/False: simple enable/disable
    - Dict: enable with metadata (priority, tags, etc.)

    Example:
      {"anthropic/claude-sonnet-4": True,
       "openai/gpt-4o": {"enabled": True, "priority": 1}}
    """

    aliases: dict[str, str] = _pydantic.Field(default_factory=dict)
    """
    User-defined shortcuts for model names.

    Key is alias, value is canonical model ID.
    Example: {"sonnet": "anthropic/claude-sonnet-4"}
    """

    registry: dict[str, ModelIdentity] = _pydantic.Field(default_factory=dict)
    """
    Full model identity registry — validated ModelIdentity objects.

    Canonical ID → ModelIdentity. All entries are validated at config
    load time. Invalid entries cause startup failure (fail-fast).

    In YAML, this is specified as nested dicts; Pydantic converts to
    ModelIdentity objects during validation.

    Example (YAML):
      registry:
        meta-llama/llama-3.3-70b-instruct:
          bindings:
            ollama: llama3.3:70b
          descriptor:
            family: llama
            series: "3.3"
            size: 70b
    """

    @_pydantic.field_validator("registry", mode="before")
    @classmethod
    def _validate_registry(
        cls,
        v: dict[str, _typing.Any] | None,
    ) -> dict[str, ModelIdentity]:
        """Convert raw dicts to ModelIdentity, injecting canonical_id."""
        if v is None:
            return {}

        result: dict[str, ModelIdentity] = {}
        for canonical_id, data in v.items():
            if isinstance(data, ModelIdentity):
                result[canonical_id] = data
            elif isinstance(data, dict):
                # Inject canonical_id if not present
                result[canonical_id] = ModelIdentity(
                    canonical_id=canonical_id,
                    **data,
                )
            else:
                raise ValueError(
                    f"Invalid registry entry for '{canonical_id}': "
                    f"expected dict or ModelIdentity, got {type(data).__name__}"
                )
        return result


# =============================================================================
# Provider Settings
# =============================================================================


class ProviderInstanceConfig(ConfigBase):
    """
    Configuration for a specific provider instance.

    YAML section: providers.instances.<name>.*

    Every provider instance MUST have a `type` field specifying the provider
    implementation to use (e.g., "ollama", "openrouter", "vllm").

    Keys:
        type: Provider type (required) - e.g., "ollama", "openrouter"
        enabled: Whether provider is enabled (bool)
        base_url: Override base URL (str, optional)
        cache_ttl: Model cache TTL in seconds (int)

    ⚠️ TEMPORARY ARCHITECTURE: Provider-specific config is read from `model_extra`
    via `extra="allow"`. Near-term follow-up will add typed per-provider schemas
    (e.g., OllamaInstanceConfig, OpenRouterInstanceConfig) for full validation.
    """

    type: str
    """Provider type (required). One of: ollama, openrouter, vllm, lmstudio, openai, etc."""

    enabled: bool = True
    """Whether this provider is enabled."""

    base_url: str | None = None
    """Override base URL (for self-hosted providers like Ollama, vLLM)."""

    cache_ttl: int = _pydantic.Field(default=3600, ge=0)
    """Model list cache TTL in seconds."""


class ProvidersConfig(ConfigBase):
    """
    Provider-related configuration.

    YAML section: providers.*

    YAML shape (users write):
        providers:
          default: openrouter
          instances:
            openrouter:
              type: openrouter
              cache_ttl: 3600
            ollama-server:
              type: ollama
              base_url: http://gpu-server:11434

    Each provider instance MUST have a `type` field specifying the provider
    implementation (openrouter, ollama, openai, etc.). The instance name can
    be anything (e.g., `ollama-server`, `ollama-local`).

    Legacy format (without `instances:` wrapper or `type:` field) is detected
    and raises an error with migration guidance.
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
        """Move dynamic provider keys into the typed instances dict.

        Also detects legacy config format (without `type` field) and provides
        helpful migration guidance.
        """
        if not isinstance(values, dict):
            return values

        reserved = {"default", "instances"}
        instances: dict[str, _typing.Any] = dict(values.pop("instances", {}) or {})

        # Move non-reserved keys to instances
        # This supports the legacy format: providers.ollama.base_url: ...
        legacy_keys: list[str] = []
        for key in list(values.keys()):
            if key not in reserved:
                config = values.pop(key)
                if isinstance(config, dict) and "type" not in config:
                    # Legacy format detected - config has no type field
                    legacy_keys.append(key)
                instances[key] = config

        # Check instances for missing type fields
        for key, config in instances.items():
            if isinstance(config, dict) and "type" not in config and key not in legacy_keys:
                legacy_keys.append(key)

        if legacy_keys:
            # Provide helpful migration guidance
            examples = []
            for key in legacy_keys[:3]:  # Show up to 3 examples
                examples.append(
                    f"    {key}:\n"
                    f"      type: {key}  # <-- Add this line\n"
                    f"      # ... other config ..."
                )
            example_text = "\n".join(examples)

            raise ValueError(
                f"Legacy provider config detected: {', '.join(legacy_keys)}\n\n"
                f"Provider instances now require an explicit 'type' field.\n\n"
                f"Old format (no longer supported):\n"
                f"  providers:\n"
                f"    ollama:\n"
                f"      base_url: http://localhost:11434\n\n"
                f"New format (required):\n"
                f"  providers:\n"
                f"    instances:\n"
                f"      ollama:\n"
                f"        type: ollama  # <-- Required!\n"
                f"        base_url: http://localhost:11434\n\n"
                f"Fix your config:\n"
                f"  providers:\n"
                f"    instances:\n"
                f"{example_text}\n"
            )

        values["instances"] = instances
        return values

    def get_provider_config(self, name: str) -> ProviderInstanceConfig | None:
        """Get config for a specific provider.

        Returns None if the provider is not configured. All provider instances
        must be explicitly declared with a `type` field.
        """
        return self.instances.get(name)


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
