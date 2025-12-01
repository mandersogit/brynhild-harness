"""
Core shared functionality for Brynhild.

This module contains logic that is shared between different UI modes
(interactive TUI, non-interactive CLI, etc.) to avoid duplication.

The core module has NO dependencies on brynhild.ui - it defines
interfaces that UI modules implement.
"""

from brynhild.core.context import (
    ContextBuilder,
    ContextInjection,
    ConversationContext,
    build_context,
)
from brynhild.core.conversation import (
    ConversationCallbacks,
    ConversationProcessor,
    ConversationResult,
)
from brynhild.core.prompts import (
    get_system_prompt,
)
from brynhild.core.tool_executor import (
    ToolExecutionCallbacks,
    ToolExecutor,
)
from brynhild.core.types import (
    ToolCallDisplay,
    ToolResultDisplay,
    format_tool_result_message,
)

__all__ = [
    # Data types (DTOs)
    "ToolCallDisplay",
    "ToolResultDisplay",
    "format_tool_result_message",
    # Context building
    "ContextBuilder",
    "ContextInjection",
    "ConversationContext",
    "build_context",
    # Prompts
    "get_system_prompt",
    # Conversation processing
    "ConversationCallbacks",
    "ConversationProcessor",
    "ConversationResult",
    # Tool execution
    "ToolExecutor",
    "ToolExecutionCallbacks",
]

