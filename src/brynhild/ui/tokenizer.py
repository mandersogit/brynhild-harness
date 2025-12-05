"""
Token counting utilities for streaming display.

This module provides client-side token counting for real-time feedback during
streaming. These counts are TEMPORARY and are replaced by provider-reported
values when the turn completes.

CRITICAL INVARIANT:
- Provider-reported usage data is ALWAYS the authoritative source.
- Client-side counts exist ONLY for temporary streaming feedback.
- Client-side counts MUST be replaced by provider data when available.

See: workflow/design-realtime-token-display.md
"""

import tiktoken as _tiktoken


def get_encoder(model: str) -> _tiktoken.Encoding:
    """
    Get a tiktoken encoder for the given model.

    Uses tiktoken's model-to-encoding mapping where available, with fallback
    to cl100k_base for unknown models.

    Model → Encoding mapping (from tiktoken):
    - gpt-oss-* → o200k_harmony (accurate)
    - gpt-4* → cl100k_base (accurate)
    - gpt-3.5* → cl100k_base (accurate)
    - Others → cl100k_base (approximate)

    Args:
        model: Model name (e.g., "gpt-oss-120b", "gpt-4", "claude-3-sonnet")

    Returns:
        A tiktoken Encoding suitable for the model.
    """
    try:
        return _tiktoken.encoding_for_model(model)
    except KeyError:
        # Unknown model - use reasonable default
        # cl100k_base is GPT-4's tokenizer, reasonable approximation for most LLMs
        return _tiktoken.get_encoding("cl100k_base")


def count_tokens(encoder: _tiktoken.Encoding, text: str) -> int:
    """
    Count the number of tokens in a text string.

    Args:
        encoder: A tiktoken Encoding instance.
        text: Text to count tokens for.

    Returns:
        Number of tokens.
    """
    return len(encoder.encode(text))


class TurnTokenCounter:
    """
    Tracks tokens generated during a single turn (streaming period).

    This counter provides real-time feedback during streaming. Its values are
    TEMPORARY and should be replaced by provider-reported totals when the turn
    completes.

    Usage:
        counter = TurnTokenCounter("gpt-oss-120b")
        counter.reset()  # At turn start
        counter.add_text(delta)  # On each text/thinking delta
        # ... streaming ...
        # When turn ends, display provider-reported value, not counter.count
    """

    def __init__(self, model: str) -> None:
        """
        Initialize with a model name for encoder selection.

        Args:
            model: Model name for tokenizer selection.
        """
        self._encoder = get_encoder(model)
        self._count = 0

    @property
    def count(self) -> int:
        """Current token count (ephemeral, for display only)."""
        return self._count

    def reset(self) -> None:
        """Reset counter at the start of a new turn."""
        self._count = 0

    def add_text(self, text: str) -> int:
        """
        Add text and return new total count.

        Args:
            text: Text delta to count.

        Returns:
            Updated total token count for this turn.
        """
        tokens = count_tokens(self._encoder, text)
        self._count += tokens
        return self._count

    @property
    def encoder_name(self) -> str:
        """Name of the encoder being used."""
        return self._encoder.name


# Type alias for optional counter
TurnTokenCounterOrNone = TurnTokenCounter | None

