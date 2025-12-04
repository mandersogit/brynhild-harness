"""
Tool system for Brynhild.

Tools are the primary interface between the LLM and the outside world.
Each tool has a schema, description, and execute method.

Usage:
    from brynhild.tools import get_default_registry, ToolResult

    registry = get_default_registry()
    tool = registry.get_or_raise("Bash")
    result = await tool.execute({"command": "echo hello"})
"""

from brynhild.tools.base import SandboxMixin, Tool, ToolResult
from brynhild.tools.bash import BashTool
from brynhild.tools.file import FileEditTool, FileReadTool, FileWriteTool
from brynhild.tools.finish import FinishTool
from brynhild.tools.glob import GlobTool
from brynhild.tools.grep import GrepTool
from brynhild.tools.inspect import InspectTool
from brynhild.tools.registry import (
    BUILTIN_TOOL_NAMES,
    ToolRegistry,
    build_registry_from_settings,
    create_default_registry,
    get_default_registry,
)
from brynhild.tools.sandbox import (
    PathValidationError,
    SandboxConfig,
    SandboxUnavailableError,
    check_read_path,
    check_write_path,
    resolve_and_validate,
    validate_path,
)
from brynhild.tools.skill import LearnSkillTool

__all__ = [
    # Base classes
    "Tool",
    "ToolResult",
    "SandboxMixin",
    # Registry
    "BUILTIN_TOOL_NAMES",
    "ToolRegistry",
    "build_registry_from_settings",
    "create_default_registry",
    "get_default_registry",
    # Sandbox
    "SandboxConfig",
    "SandboxUnavailableError",
    "PathValidationError",
    "validate_path",
    "resolve_and_validate",
    "check_read_path",
    "check_write_path",
    # Tool implementations
    "BashTool",
    "FileReadTool",
    "FileWriteTool",
    "FileEditTool",
    "FinishTool",
    "GrepTool",
    "GlobTool",
    "InspectTool",
    "LearnSkillTool",
]
