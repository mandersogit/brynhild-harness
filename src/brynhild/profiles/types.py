"""
Type definitions for model profiles.
"""

from __future__ import annotations

import dataclasses as _dataclasses
import typing as _typing


@_dataclasses.dataclass
class ModelProfile:
    """
    Model-specific configuration bundle.

    A profile contains all the settings needed to optimize Brynhild's
    behavior for a specific model or model family.
    """

    # Identity
    name: str
    """Unique profile name (e.g., 'gpt-oss-120b')."""

    family: str = ""
    """Model family for fallback matching (e.g., 'gpt-oss')."""

    description: str = ""
    """Human-readable description of the profile."""

    # API defaults
    default_temperature: float = 0.7
    """Default temperature for completions."""

    default_max_tokens: int = 8192
    """Default max tokens for responses."""

    min_max_tokens: int | None = None
    """Minimum max_tokens to use (enforced when profile is active).

    Some models (like reasoning models) need more tokens to produce useful
    output because they use tokens for internal thinking. This floor ensures
    requests don't fail due to insufficient token budget.
    """

    supports_tools: bool = True
    """Whether this model supports tool/function calling."""

    supports_reasoning: bool = False
    """Whether this model supports reasoning traces."""

    supports_streaming: bool = True
    """Whether this model supports streaming responses."""

    # Model-specific API parameters
    api_params: dict[str, _typing.Any] = _dataclasses.field(default_factory=dict)
    """
    Additional API parameters to pass to the provider.

    Examples:
        - reasoning_effort: "medium"
        - verbosity: "low"
    """

    # System prompt components
    system_prompt_prefix: str = ""
    """Text added before the base system prompt."""

    system_prompt_suffix: str = ""
    """Text added after the base system prompt."""

    prompt_patterns: dict[str, str] = _dataclasses.field(default_factory=dict)
    """
    Named prompt patterns that can be enabled/disabled.

    Keys are pattern names (e.g., 'persistence', 'tool_policy').
    Values are the prompt text to include.
    """

    enabled_patterns: list[str] = _dataclasses.field(default_factory=list)
    """List of pattern names from prompt_patterns to include in system prompt."""

    # Tool configuration
    tool_format: str = "openai"
    """Tool schema format: 'openai', 'anthropic', or 'custom'."""

    tool_parallelization: bool = True
    """Whether to allow parallel tool calls."""

    max_tools_per_turn: int | None = None
    """Maximum tool calls per turn (None = unlimited)."""

    # Behavioral settings
    eagerness: _typing.Literal["minimal", "low", "medium", "high"] = "medium"
    """How proactive vs. waiting for guidance."""

    verbosity: _typing.Literal["low", "medium", "high"] = "medium"
    """Output length preference."""

    thoroughness: _typing.Literal["fast", "balanced", "thorough"] = "balanced"
    """Speed vs. completeness tradeoff."""

    # Stuck detection
    stuck_detection_enabled: bool = True
    """Whether to detect stuck/looping behavior."""

    max_similar_tool_calls: int = 3
    """How many similar tool calls before triggering stuck detection."""

    # Provider-specific overrides
    provider_specific: dict[str, _typing.Any] = _dataclasses.field(default_factory=dict)
    """Provider-specific configuration overrides."""

    def get_enabled_patterns_text(self) -> str:
        """Get concatenated text of all enabled prompt patterns."""
        parts = []
        for name in self.enabled_patterns:
            if name in self.prompt_patterns:
                parts.append(self.prompt_patterns[name])
        return "\n\n".join(parts)

    def build_system_prompt(self, base_prompt: str) -> str:
        """
        Build the full system prompt with profile patterns.

        Args:
            base_prompt: The base system prompt to enhance.

        Returns:
            Full system prompt with prefix, patterns, base, and suffix.
        """
        parts = []

        if self.system_prompt_prefix:
            parts.append(self.system_prompt_prefix)

        patterns_text = self.get_enabled_patterns_text()
        if patterns_text:
            parts.append(patterns_text)

        parts.append(base_prompt)

        if self.system_prompt_suffix:
            parts.append(self.system_prompt_suffix)

        return "\n\n".join(parts)

    def to_dict(self) -> dict[str, _typing.Any]:
        """Convert profile to dictionary for serialization."""
        return _dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, _typing.Any]) -> ModelProfile:
        """Create profile from dictionary."""
        return cls(**data)

