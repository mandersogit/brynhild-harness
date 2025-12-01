"""
Hook system for Brynhild.

Hooks enable extensibility by allowing users to respond to lifecycle events
during agent execution. Hooks can intercept, modify, or block operations
without modifying core code.

Example usage:
    from brynhild.hooks import HookManager, HookEvent, HookContext

    manager = HookManager.from_config()
    result = await manager.dispatch(
        HookEvent.PRE_TOOL_USE,
        HookContext(
            event=HookEvent.PRE_TOOL_USE,
            session_id="abc123",
            cwd=Path.cwd(),
            tool="Bash",
            tool_input={"command": "ls -la"},
        ),
    )
    if result.action == HookAction.BLOCK:
        # Hook blocked the operation
        ...
"""

from brynhild.hooks.compaction import (
    CompactionResult,
    ContextCompactor,
    compact_messages,
)
from brynhild.hooks.events import (
    HookAction,
    HookContext,
    HookEvent,
    HookResult,
)
from brynhild.hooks.manager import HookManager
from brynhild.hooks.stuck import (
    StuckDetector,
    StuckState,
)

__all__ = [
    "CompactionResult",
    "ContextCompactor",
    "HookAction",
    "HookContext",
    "HookEvent",
    "HookManager",
    "HookResult",
    "StuckDetector",
    "StuckState",
    "compact_messages",
]

