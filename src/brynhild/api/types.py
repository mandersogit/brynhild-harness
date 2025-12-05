"""
Type definitions for LLM API interactions.

These types provide a provider-agnostic interface for working with LLM responses.
"""

from __future__ import annotations

import dataclasses as _dataclasses
import typing as _typing


@_dataclasses.dataclass
class UsageDetails:
    """Detailed token usage breakdown (provider-specific)."""

    # Token breakdown
    reasoning_tokens: int | None = None
    """Tokens used for reasoning/thinking (subset of output_tokens)."""

    cached_tokens: int | None = None
    """Tokens served from cache (subset of input_tokens)."""

    # Cost information (USD)
    cost: float | None = None
    """Total cost in USD for this request."""

    prompt_cost: float | None = None
    """Cost for input/prompt tokens."""

    completion_cost: float | None = None
    """Cost for output/completion tokens."""

    # Provider metadata
    provider: str | None = None
    """Actual provider that served the request (e.g., 'Novita' for OpenRouter)."""

    generation_id: str | None = None
    """Unique ID for this generation (for debugging/support)."""


@_dataclasses.dataclass
class Usage:
    """Token usage information."""

    input_tokens: int = 0
    output_tokens: int = 0

    # Extended details (may be None for providers that don't support them)
    details: UsageDetails | None = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cost(self) -> float | None:
        """Convenience accessor for cost."""
        return self.details.cost if self.details else None

    @property
    def reasoning_tokens(self) -> int | None:
        """Convenience accessor for reasoning tokens."""
        return self.details.reasoning_tokens if self.details else None


@_dataclasses.dataclass
class ToolUse:
    """A tool use request from the model."""

    id: str
    name: str
    input: dict[str, _typing.Any]


@_dataclasses.dataclass
class ToolResult:
    """Result of executing a tool."""

    tool_use_id: str
    content: str
    is_error: bool = False


@_dataclasses.dataclass
class StreamEvent:
    """
    Provider-agnostic stream event.

    Different providers emit different event types, but we normalize them
    to this common structure.
    """

    type: _typing.Literal[
        "message_start",
        "content_start",
        "text_delta",
        "thinking_delta",  # For reasoning/thinking traces
        "tool_use_start",
        "tool_use_delta",
        "content_stop",
        "message_delta",
        "message_stop",
        "error",
    ]

    # Text content (for text_delta events)
    text: str | None = None

    # Thinking/reasoning content (for thinking_delta events)
    thinking: str | None = None

    # Tool use (for tool_use_* events)
    tool_use: ToolUse | None = None

    # Partial tool input JSON (for tool_use_delta)
    tool_input_delta: str | None = None

    # Usage info (for message_delta/message_stop)
    usage: Usage | None = None

    # Error info (for error events)
    error: str | None = None

    # Message ID (for message_start)
    message_id: str | None = None

    # Stop reason (for message_stop)
    stop_reason: str | None = None


@_dataclasses.dataclass
class Message:
    """A message in the conversation."""

    role: _typing.Literal["user", "assistant"]
    content: str | list[ContentBlock]


@_dataclasses.dataclass
class ContentBlock:
    """A content block within a message (text or tool use/result)."""

    type: _typing.Literal["text", "tool_use", "tool_result"]

    # For text blocks
    text: str | None = None

    # For tool_use blocks
    id: str | None = None
    name: str | None = None
    input: dict[str, _typing.Any] | None = None

    # For tool_result blocks
    tool_use_id: str | None = None
    content: str | None = None
    is_error: bool = False


@_dataclasses.dataclass
class Tool:
    """Tool definition for the API."""

    name: str
    description: str
    input_schema: dict[str, _typing.Any]

    def to_anthropic_format(self) -> dict[str, _typing.Any]:
        """Convert to Anthropic API format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def to_openai_format(self) -> dict[str, _typing.Any]:
        """Convert to OpenAI/OpenRouter format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


@_dataclasses.dataclass
class CompletionResponse:
    """Complete response from a non-streaming API call."""

    id: str
    content: str
    stop_reason: str | None
    usage: Usage
    tool_uses: list[ToolUse] = _dataclasses.field(default_factory=list)
    thinking: str | None = None  # Reasoning/thinking trace if available

    @property
    def has_tool_use(self) -> bool:
        return len(self.tool_uses) > 0
