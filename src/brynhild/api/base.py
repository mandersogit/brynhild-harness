"""
Abstract base class for LLM providers.

All providers (Anthropic, OpenRouter, Bedrock, Vertex) implement this interface.
"""

from __future__ import annotations

import abc as _abc
import logging as _logging
import typing as _typing

import brynhild.api.types as types
import brynhild.constants as _constants

_logger = _logging.getLogger(__name__)

if _typing.TYPE_CHECKING:
    import brynhild.profiles.types as profile_types


# How to format reasoning/thinking when sending messages back to the model
ReasoningFormat = _typing.Literal["reasoning_field", "thinking_tags", "none"]
"""
Options for how reasoning is included in conversation history:

- "reasoning_field": Send as a separate `reasoning` field on the message.
  This is the OpenRouter convention and allows providers to properly
  translate it to Harmony's analysis channel.

- "thinking_tags": Wrap reasoning in <thinking>...</thinking> tags in the
  content field. More universal but the model sees it as content, not in
  the proper reasoning channel.

- "none": Don't include reasoning in history at all. Simplest but the model
  loses context about its reasoning between tool calls.
"""

# How much reasoning/thinking depth to request from the model
# Using str instead of Literal to allow provider-specific values with "raw:" prefix
ReasoningLevel = str
"""
Type alias for reasoning level values.

Standard levels: "auto", "off", "minimal", "low", "medium", "high", "maximum"

Custom values can be passed with "raw:" prefix to suppress unknown-level warnings:
- "raw:thinking_budget=65536" — provider interprets literally
- "raw:effort_high" — provider-specific level name
"""

# Known standard reasoning levels
KNOWN_REASONING_LEVELS: frozenset[str] = frozenset({
    "auto", "off", "minimal", "low", "medium", "high", "maximum"
})
"""
Standard reasoning levels that are recognized without warning.

- "auto": Let the model/provider decide (default)
- "off": Disable extended thinking entirely
- "minimal": Very brief reasoning
- "low": Light reasoning
- "medium": Moderate reasoning
- "high": Deep reasoning
- "maximum": Maximum reasoning depth

Providers translate these to their native format. Common mappings:
- Gemini 3: thinking_level (minimal/low/medium/high)
- Gemini 2.5: thinking_budget (token count)
- Claude: Extended thinking on/off
- OpenAI o1/o3: reasoning effort
"""

# Prefix for raw/passthrough reasoning level values
RAW_REASONING_PREFIX: str = "raw:"


def parse_reasoning_level(value: str) -> tuple[str, bool]:
    """
    Parse a reasoning level value, detecting raw prefix.

    Args:
        value: The reasoning level string from config

    Returns:
        Tuple of (level, is_raw) where:
        - level: The actual level value (prefix stripped if raw)
        - is_raw: True if "raw:" prefix was present
    """
    if value.startswith(RAW_REASONING_PREFIX):
        return value[len(RAW_REASONING_PREFIX):], True
    return value, False


class LLMProvider(_abc.ABC):
    """
    Abstract base for LLM providers.

    Implementations handle the specifics of each provider's API while
    presenting a unified interface.

    Providers can have an associated ModelProfile that is automatically applied
    to enhance system prompts with model-specific patterns.
    """

    _profile: profile_types.ModelProfile | None = None
    _raw_logger: _typing.Any = None  # RawPayloadLogger, but avoid circular import

    @property
    @_abc.abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'anthropic', 'openrouter')."""
        ...

    @property
    @_abc.abstractmethod
    def model(self) -> str:
        """Current model being used."""
        ...

    @property
    def profile(self) -> profile_types.ModelProfile | None:
        """Model profile for this provider, if any."""
        return self._profile

    @profile.setter
    def profile(self, value: profile_types.ModelProfile | None) -> None:
        """Set the model profile."""
        self._profile = value

    @property
    def raw_logger(self) -> _typing.Any:
        """Raw payload logger for debugging."""
        return self._raw_logger

    @raw_logger.setter
    def raw_logger(self, value: _typing.Any) -> None:
        """Set the raw payload logger."""
        self._raw_logger = value

    def apply_profile_to_system(self, system: str | None) -> str | None:
        """
        Apply the model profile to a system prompt.

        If a profile is set, wraps the system prompt with profile patterns.
        If no profile is set, returns the system prompt unchanged.

        Args:
            system: Base system prompt (or None)

        Returns:
            Enhanced system prompt with profile patterns, or original if no profile
        """
        if self._profile is None:
            return system

        base = system or ""
        return self._profile.build_system_prompt(base)

    def apply_profile_to_max_tokens(self, max_tokens: int) -> int:
        """
        Apply the model profile's min_max_tokens constraint.

        If a profile is set with min_max_tokens, ensures max_tokens is at least
        that value. This is needed for reasoning models that use tokens for
        internal thinking.

        Args:
            max_tokens: Requested max_tokens value

        Returns:
            Adjusted max_tokens (at least profile.min_max_tokens if set)
        """
        if self._profile is None:
            return max_tokens

        min_tokens = self._profile.min_max_tokens
        if min_tokens is not None and max_tokens < min_tokens:
            return min_tokens

        return max_tokens

    @_abc.abstractmethod
    def supports_tools(self) -> bool:
        """Whether this provider/model supports tool use."""
        ...

    def supports_reasoning(self) -> bool:
        """Whether this provider/model supports extended thinking/reasoning."""
        return False

    @property
    def default_reasoning_level(self) -> ReasoningLevel:
        """
        Default reasoning level for this provider/model.

        Providers can override this to specify their preferred default.
        Users can also override via BRYNHILD_BEHAVIOR__REASONING_LEVEL setting.

        Returns:
            The provider's default reasoning level.
        """
        return "auto"  # Safe default - let provider/model decide

    def get_reasoning_level(self) -> ReasoningLevel:
        """
        Get the effective reasoning level, checking user override first.

        Checks:
        1. User config (behavior.reasoning_level)
        2. Falls back to provider's default_reasoning_level

        Parses "raw:" prefix for custom values. Warns on unknown levels
        that don't have the "raw:" prefix.

        Returns:
            The reasoning level to use for requests (prefix stripped if raw).
        """
        try:
            import brynhild.config as config

            settings = config.Settings()
            if settings.reasoning_level != "auto":
                # User has explicitly set a level - parse it
                level, is_raw = parse_reasoning_level(settings.reasoning_level)

                # Warn on unknown levels without raw: prefix
                if not is_raw and level not in KNOWN_REASONING_LEVELS:
                    _logger.warning(
                        "Unknown reasoning_level '%s' — use 'raw:%s' to suppress this warning",
                        level,
                        level,
                    )

                return level
        except Exception:
            pass  # Fall back to provider default if settings unavailable

        return self.default_reasoning_level

    def translate_reasoning_level(
        self,
        level: ReasoningLevel | None = None,  # noqa: ARG002 - subclasses use this
    ) -> dict[str, _typing.Any]:
        """
        Translate unified reasoning level to provider-specific parameters.

        Override this in provider subclasses to return the appropriate
        native parameters for your provider's API.

        Args:
            level: Reasoning level to translate. If None, uses get_reasoning_level().

        Returns:
            Dict of provider-specific parameters to include in API requests.
            Empty dict if reasoning level doesn't affect this provider.

        Example implementation for Gemini 3:
            if level in ("minimal", "low", "medium", "high"):
                return {"thinking_level": level}
            return {}

        Example implementation for Gemini 2.5:
            budget_map = {"minimal": 1024, "low": 4096, "medium": 16384, "high": 65536}
            return {"thinking_budget": budget_map.get(level, 8192)}
        """
        # Base implementation returns empty dict - providers override as needed
        return {}

    @property
    def default_reasoning_format(self) -> ReasoningFormat:
        """
        Default format for including reasoning in conversation history.

        Providers can override this to specify their preferred format.
        Users can also override via BRYNHILD_REASONING_FORMAT setting.

        Returns:
            The provider's default reasoning format.
        """
        return "none"  # Safe default - providers that support it should override

    @_abc.abstractmethod
    async def complete(
        self,
        messages: list[dict[str, _typing.Any]],
        *,
        system: str | None = None,
        tools: list[types.Tool] | None = None,
        max_tokens: int = _constants.DEFAULT_MAX_TOKENS,
        use_profile: bool = True,
    ) -> types.CompletionResponse:
        """
        Send messages and get a complete response (non-streaming).

        Args:
            messages: Conversation messages in provider-agnostic format
            system: Optional system prompt
            tools: Optional list of tools available to the model
            max_tokens: Maximum tokens in the response
            use_profile: Whether to apply the model profile (default True)

        Returns:
            Complete response with content and usage info
        """
        ...

    @_abc.abstractmethod
    def stream(
        self,
        messages: list[dict[str, _typing.Any]],
        *,
        system: str | None = None,
        tools: list[types.Tool] | None = None,
        max_tokens: int = _constants.DEFAULT_MAX_TOKENS,
        use_profile: bool = True,
    ) -> _typing.AsyncIterator[types.StreamEvent]:
        """
        Stream messages and yield events as they arrive.

        Note: This method is not async itself, but returns an async iterator.
        Implementations should use 'async def' which returns an async generator.

        Args:
            messages: Conversation messages in provider-agnostic format
            system: Optional system prompt
            tools: Optional list of tools available to the model
            max_tokens: Maximum tokens in the response
            use_profile: Whether to apply the model profile (default True)

        Yields:
            StreamEvent objects as the response is generated
        """
        ...

    async def test_connection(self) -> dict[str, _typing.Any]:
        """
        Test the connection to the provider.

        Returns:
            Dict with status, latency, and any errors
        """
        import time as _time

        start = _time.perf_counter()
        try:
            # Simple test message
            response = await self.complete(
                messages=[{"role": "user", "content": "Say 'ok'"}],
                max_tokens=10,
            )
            latency_ms = int((_time.perf_counter() - start) * 1000)
            return {
                "status": "ok",
                "provider": self.name,
                "model": self.model,
                "latency_ms": latency_ms,
                "response": response.content[:50],
            }
        except Exception as e:
            latency_ms = int((_time.perf_counter() - start) * 1000)
            return {
                "status": "error",
                "provider": self.name,
                "model": self.model,
                "latency_ms": latency_ms,
                "error": str(e),
            }
