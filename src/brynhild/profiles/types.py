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
    """Human-readable description of the profile.

    Note: Display only; no effect on system behavior.
    """

    # API defaults
    default_temperature: float = 0.7
    """Default temperature for completions.

    Note: Display only; provider uses its own temperature setting.
    """

    default_max_tokens: int = 8192
    """Default max tokens for responses.

    Note: Display only; not enforced. Use min_max_tokens for enforcement.
    """

    min_max_tokens: int | None = None
    """Minimum max_tokens to use (enforced when profile is active).

    Some models (like reasoning models) need more tokens to produce useful
    output because they use tokens for internal thinking. This floor ensures
    requests don't fail due to insufficient token budget.
    """

    supports_tools: bool = True
    """Whether this model supports tool/function calling.

    Note: Display only; provider has its own supports_tools() method.
    """

    supports_reasoning: bool = False
    """Whether this model supports reasoning traces.

    Note: Display only; provider has its own supports_reasoning() method.
    """

    supports_streaming: bool = True
    """Whether this model supports streaming responses.

    Note: Display only; no effect on system behavior.
    """

    # Model-specific API parameters
    api_params: dict[str, _typing.Any] = _dataclasses.field(default_factory=dict)
    """
    Additional API parameters to pass to the provider.

    Examples:
        - reasoning_effort: "medium"
        - verbosity: "low"

    Note: Display only; NOT actually passed to provider.
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
    # NOTE: These tool fields are aspirational; none currently affect behavior.
    tool_format: str = "openai"
    """Tool schema format: 'openai', 'anthropic', or 'custom'.

    Note: Aspirational; no current effect on system behavior.
    """

    tool_parallelization: bool = True
    """Whether to allow parallel tool calls.

    Note: Aspirational; no current effect on system behavior.
    """

    max_tools_per_turn: int | None = None
    """Maximum tool calls per turn (None = unlimited).

    Note: Aspirational; no current effect on system behavior.
    """

    # Tool call recovery settings
    enable_tool_recovery: bool = False
    """Whether to attempt recovery of tool calls from thinking text.

    Some models place tool call JSON in their thinking/reasoning output instead
    of emitting it via the proper tool_calls API channel. When enabled, Brynhild
    will scan thinking text for JSON matching tool schemas and execute recovered
    calls. Default is False to avoid masking issues with reliable models.
    """

    recovery_feedback_enabled: bool = True
    """Whether to inject feedback after recovering a tool call.

    When True, after a successful recovery, Brynhild injects a message to the
    model explaining that it placed tool arguments in thinking instead of the
    tool call channel. This can help the model self-correct in subsequent turns.
    """

    recovery_requires_intent_phrase: bool = False
    """Whether to require intent phrases near JSON for recovery.

    When True, tool call recovery requires evidence of intent (e.g., "I will call X",
    "Let me use the Y tool") within 200 characters before the JSON. This reduces
    false positives but may miss some legitimate tool calls.
    """

    # Behavioral settings
    # NOTE: These behavioral fields are display-only; none currently affect behavior.
    eagerness: _typing.Literal["minimal", "low", "medium", "high"] = "medium"
    """How proactive vs. waiting for guidance.

    Note: Display only; no current effect on system behavior.
    """

    verbosity: _typing.Literal["low", "medium", "high"] = "medium"
    """Output length preference.

    Note: Display only; no current effect on system behavior.
    """

    thoroughness: _typing.Literal["fast", "balanced", "thorough"] = "balanced"
    """Speed vs. completeness tradeoff.

    Note: Display only; no current effect on system behavior.
    """

    # Stuck detection
    # NOTE: These stuck detection fields are aspirational; none currently affect behavior.
    stuck_detection_enabled: bool = True
    """Whether to detect stuck/looping behavior.

    Note: Aspirational; no current effect on system behavior.
    """

    max_similar_tool_calls: int = 3
    """How many similar tool calls before triggering stuck detection.

    Note: Aspirational; no current effect on system behavior.
    """

    # Provider-specific overrides
    provider_specific: dict[str, _typing.Any] = _dataclasses.field(default_factory=dict)
    """Provider-specific configuration overrides.

    Note: Aspirational; no current effect on system behavior.
    """

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
