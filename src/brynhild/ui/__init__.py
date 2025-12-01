"""
UI module for Brynhild.

Provides terminal UI components built in testable layers:
- Layer 1: PlainTextRenderer - Just strings, fully testable
- Layer 2: JSONRenderer - Structured output, machine-readable
- Layer 3: RichConsoleRenderer - Colors and formatting
- Layer 4: TextualTUI - Full interactive app
"""

import typing as _typing

# Callback adapters (implement core interfaces using UI components)
from brynhild.ui.adapters import (
    AsyncCallbackAdapter,
    RendererCallbacks,
    SyncCallbackAdapter,
)

# Base types - ToolCallDisplay and ToolResultDisplay now live in core.types
# but are re-exported from ui.base for backwards compatibility
from brynhild.ui.base import (
    ConversationResult,
    Renderer,
    ToolCallDisplay,
    ToolResultDisplay,
)
from brynhild.ui.json_renderer import JSONRenderer
from brynhild.ui.plain import CaptureRenderer, PlainTextRenderer
from brynhild.ui.rich_renderer import RichConsoleRenderer
from brynhild.ui.runner import ConversationRunner


def __getattr__(name: str) -> _typing.Any:
    """Lazy import for app and widget modules to avoid circular imports."""
    if name == "BrynhildApp":
        from brynhild.ui.app import BrynhildApp

        return BrynhildApp
    if name == "create_app":
        from brynhild.ui.app import create_app

        return create_app
    if name in ("MessageWidget", "StreamingMessageWidget", "PermissionDialog"):
        import brynhild.ui.widgets as widgets

        return getattr(widgets, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Base types (re-exported from core.types for backwards compatibility)
    "Renderer",
    "ToolCallDisplay",
    "ToolResultDisplay",
    "ConversationResult",
    # Callback adapters (implement core interfaces)
    "RendererCallbacks",
    "SyncCallbackAdapter",
    "AsyncCallbackAdapter",
    # Renderers
    "PlainTextRenderer",
    "CaptureRenderer",
    "JSONRenderer",
    "RichConsoleRenderer",
    # Runner
    "ConversationRunner",
    # TUI App (Layer 4) - lazy loaded
    "BrynhildApp",
    "create_app",
    # Widgets - lazy loaded
    "MessageWidget",
    "StreamingMessageWidget",
    "PermissionDialog",
]
