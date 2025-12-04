"""
Icon utilities for consistent terminal display.

Unicode emojis/icons render at different widths across terminals, fonts,
and systems. This module provides cell-width-aware padding functions that
normalize widths using Rich's cell_len for better visual alignment.
"""

import rich.cells as _rich_cells

# =============================================================================
# Icon Constants
# =============================================================================

ICON_WARNING = "⚠️"      # Recovered tool call, permission required
ICON_BOLT = "⚡"          # Native tool call
ICON_SUCCESS = "✓"       # Success/enabled
ICON_FAILURE = "✗"       # Failure/disabled
ICON_RECOVERED = "↺"     # Recovery indicator (alternative to warning)

# Default target width for icon + padding (in terminal cells)
DEFAULT_ICON_WIDTH = 3


# =============================================================================
# Cell-Width-Aware String Padding
# =============================================================================


def cell_ljust(text: str, width: int) -> str:
    """Left-justify text to a cell width (pad on right).

    Like str.ljust() but uses terminal cell width instead of character count.

    Args:
        text: The text to pad.
        width: Target width in terminal cells.

    Returns:
        Text with trailing spaces to reach width.
    """
    current = _rich_cells.cell_len(text)
    return text + " " * max(0, width - current)


def cell_rjust(text: str, width: int) -> str:
    """Right-justify text to a cell width (pad on left).

    Like str.rjust() but uses terminal cell width instead of character count.

    Args:
        text: The text to pad.
        width: Target width in terminal cells.

    Returns:
        Text with leading spaces to reach width.
    """
    current = _rich_cells.cell_len(text)
    return " " * max(0, width - current) + text


def cell_center(text: str, width: int) -> str:
    """Center text to a cell width (pad both sides).

    Like str.center() but uses terminal cell width instead of character count.

    Args:
        text: The text to pad.
        width: Target width in terminal cells.

    Returns:
        Text with spaces on both sides to reach width.
    """
    current = _rich_cells.cell_len(text)
    padding = max(0, width - current)
    left = padding // 2
    return " " * left + text + " " * (padding - left)


# =============================================================================
# Convenience Functions
# =============================================================================
#
# These use left-justify by default because icons are typically followed by
# text (e.g., "⚡ file_read"). Use cell_center() directly for standalone icons.


def icon_warning() -> str:
    """Padded warning icon (⚠️) for recovered calls and permissions."""
    return cell_ljust(ICON_WARNING, DEFAULT_ICON_WIDTH)


def icon_bolt() -> str:
    """Padded bolt icon (⚡) for native tool calls."""
    return cell_ljust(ICON_BOLT, DEFAULT_ICON_WIDTH)


def icon_success() -> str:
    """Padded success icon (✓) for successful results."""
    return cell_ljust(ICON_SUCCESS, DEFAULT_ICON_WIDTH)


def icon_failure() -> str:
    """Padded failure icon (✗) for failed results."""
    return cell_ljust(ICON_FAILURE, DEFAULT_ICON_WIDTH)


def icon_recovered() -> str:
    """Padded recovery icon (↺) for recovered tool calls."""
    return cell_ljust(ICON_RECOVERED, DEFAULT_ICON_WIDTH)
