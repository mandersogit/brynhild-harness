"""
Hook executors - responsible for running different hook types.

Each executor handles a specific hook type:
- CommandHookExecutor: Runs shell commands
- ScriptHookExecutor: Runs Python scripts with JSON I/O
- PromptHookExecutor: Calls LLM for decisions
"""

from __future__ import annotations

import pathlib as _pathlib
import typing as _typing

from brynhild.hooks.executors.base import HookExecutor
from brynhild.hooks.executors.command import CommandHookExecutor
from brynhild.hooks.executors.script import ScriptHookExecutor

__all__ = [
    "CommandHookExecutor",
    "HookExecutor",
    "ScriptHookExecutor",
    "create_executor",
]


def create_executor(
    hook_type: _typing.Literal["command", "script", "prompt"],
    *,
    project_root: _pathlib.Path | None = None,
) -> HookExecutor:
    """
    Create an executor for the given hook type.

    Args:
        hook_type: Type of hook to execute.
        project_root: Project root directory.

    Returns:
        Appropriate executor instance.

    Raises:
        ValueError: If hook type is unknown.
    """
    if hook_type == "command":
        return CommandHookExecutor(project_root=project_root)
    elif hook_type == "script":
        return ScriptHookExecutor(project_root=project_root)
    elif hook_type == "prompt":
        # Import here to avoid circular imports and heavy deps
        from brynhild.hooks.executors.prompt import PromptHookExecutor

        return PromptHookExecutor(project_root=project_root)
    else:
        raise ValueError(f"Unknown hook type: {hook_type}")

