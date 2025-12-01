"""
System prompts for Brynhild.

This module contains the system prompt generation used across all UI modes.
Changes here affect both interactive and non-interactive modes.
"""

import typing as _typing

if _typing.TYPE_CHECKING:
    import brynhild.tools.registry as _registry

# System prompt intro (before tool list)
_SYSTEM_PROMPT_INTRO = """\
You are Brynhild, an open-source AI coding harness. You are powered by {model_name}.

You help users with programming tasks by reading, writing, and editing code files,
searching codebases, and executing shell commands.
"""

# System prompt guidelines (after tool list)
_GUIDELINES_BASH_AVAILABLE = """\
IMPORTANT: For filesystem queries (listing files, finding oldest/newest/largest files,
checking if files exist), ALWAYS use Inspect instead of Bash. Inspect is faster,
cross-platform, and doesn't require user permission.

"""

_GUIDELINES_BASE = """\
When the user asks you to perform a task:
1. Use the appropriate tools to accomplish it
2. Explain what you're doing
3. Show relevant results

Be concise but helpful. When editing code, preserve existing style and conventions.
"""


def _format_tool_list(tool_registry: "_registry.ToolRegistry") -> str:
    """
    Generate tool list section from the registry.

    Args:
        tool_registry: Registry containing available tools.

    Returns:
        Formatted tool list for the system prompt.
    """
    tools = tool_registry.list_tools()
    if not tools:
        return "You have no tools available."

    lines = ["You have access to the following tools:"]
    for tool in tools:
        lines.append(f"- {tool.name}: {tool.description}")

    return "\n".join(lines)


def _get_guidelines(tool_registry: "_registry.ToolRegistry") -> str:
    """Get guidelines section, conditional on available tools."""
    parts: list[str] = []

    # Only include Bash-vs-Inspect guidance if both are available
    tool_names = tool_registry.list_names()
    if "Bash" in tool_names and "Inspect" in tool_names:
        parts.append(_GUIDELINES_BASH_AVAILABLE)

    parts.append(_GUIDELINES_BASE)
    return "".join(parts)


def get_system_prompt(
    model_name: str,
    tool_registry: "_registry.ToolRegistry",
) -> str:
    """Generate the system prompt with model name and available tools.

    Args:
        model_name: The model identifier (e.g., 'anthropic/claude-sonnet-4')
        tool_registry: Registry containing available tools.

    Returns:
        The complete system prompt.
    """
    intro = _SYSTEM_PROMPT_INTRO.format(model_name=model_name)
    tool_list = _format_tool_list(tool_registry)
    guidelines = _get_guidelines(tool_registry)

    return f"{intro}\n{tool_list}\n\n{guidelines}"
