"""
Tool registry for managing available tools.

The registry provides a central place to register, look up, and list tools.
"""

from __future__ import annotations

import typing as _typing

import brynhild.tools.base as base


class ToolRegistry:
    """
    Registry for tool instances.

    Tools can be registered by name and looked up for execution.
    The registry also provides listing and schema introspection.
    """

    def __init__(self) -> None:
        self._tools: dict[str, base.Tool] = {}

    def register(self, tool: base.Tool) -> None:
        """
        Register a tool instance.

        Args:
            tool: Tool instance to register

        Raises:
            ValueError: If a tool with the same name is already registered
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> base.Tool | None:
        """
        Get a tool by name.

        Args:
            name: Tool name (case-sensitive)

        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(name)

    def get_or_raise(self, name: str) -> base.Tool:
        """
        Get a tool by name, raising if not found.

        Args:
            name: Tool name (case-sensitive)

        Returns:
            Tool instance

        Raises:
            KeyError: If tool is not found
        """
        tool = self._tools.get(name)
        if tool is None:
            available = ", ".join(sorted(self._tools.keys()))
            raise KeyError(f"Tool '{name}' not found. Available: {available}")
        return tool

    def list_tools(self) -> list[base.Tool]:
        """
        List all registered tools.

        Returns:
            List of tool instances, sorted by name
        """
        return sorted(self._tools.values(), key=lambda t: t.name)

    def list_names(self) -> list[str]:
        """
        List names of all registered tools.

        Returns:
            Sorted list of tool names
        """
        return sorted(self._tools.keys())

    def to_api_format(self) -> list[dict[str, _typing.Any]]:
        """
        Get all tools in Anthropic API format.

        Returns:
            List of tool definitions for the API
        """
        return [tool.to_api_format() for tool in self.list_tools()]

    def to_openai_format(self) -> list[dict[str, _typing.Any]]:
        """
        Get all tools in OpenAI/OpenRouter API format.

        Returns:
            List of tool definitions for the API
        """
        return [tool.to_openai_format() for tool in self.list_tools()]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __iter__(self) -> _typing.Iterator[base.Tool]:
        return iter(self.list_tools())


# Global default registry
_default_registry: ToolRegistry | None = None


def get_default_registry() -> ToolRegistry:
    """
    Get the default tool registry.

    The default registry is lazily initialized with all built-in tools.

    Returns:
        The default ToolRegistry instance
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = create_default_registry()
    return _default_registry


def create_default_registry() -> ToolRegistry:
    """
    Create a new registry with all built-in tools using default settings.

    Returns:
        New ToolRegistry with built-in tools registered
    """
    # Import here to avoid circular imports
    import brynhild.config as config

    settings = config.Settings()
    return build_registry_from_settings(settings)


def build_registry_from_settings(
    settings: _typing.Any,  # brynhild.config.Settings, but avoid circular import
) -> ToolRegistry:
    """
    Build a tool registry configured from Settings.

    This ensures all tools are configured with:
    - Proper project root
    - Sandbox settings (enabled, allowed paths, network)
    - Consistent base directories
    - Respects disabled_tools and disable_builtin_tools settings

    Args:
        settings: Settings instance with sandbox configuration

    Returns:
        New ToolRegistry with properly configured tools
    """
    # Import tools here to avoid circular imports
    import brynhild.tools.bash as bash
    import brynhild.tools.file as file
    import brynhild.tools.glob as glob_tool
    import brynhild.tools.grep as grep
    import brynhild.tools.inspect as inspect_tool
    import brynhild.tools.sandbox as sandbox

    registry = ToolRegistry()

    # If all builtin tools are disabled, return empty registry
    disable_all = getattr(settings, "disable_builtin_tools", False)
    if disable_all:
        return registry

    # Get set of specifically disabled tools
    disabled_tools: set[str] = getattr(settings, "get_disabled_tools", lambda: set())()

    project_root = settings.project_root
    allowed_paths = settings.get_allowed_paths()

    # Determine if sandbox should be skipped
    skip_sandbox = getattr(settings, "dangerously_skip_sandbox", False)

    # Create shared sandbox config
    sandbox_config = sandbox.SandboxConfig(
        project_root=project_root,
        allowed_paths=allowed_paths,
        allow_network=settings.sandbox_allow_network,
        skip_sandbox=skip_sandbox,
    )

    # Register Bash tool with sandbox settings
    if "Bash" not in disabled_tools:
        bash_tool = bash.BashTool(
            working_dir=project_root,
            sandbox_enabled=settings.sandbox_enabled and not skip_sandbox,
        )
        bash_tool.configure_sandbox(
            project_root=project_root,
            allowed_paths=allowed_paths,
            allow_network=settings.sandbox_allow_network,
        )
        # Apply skip_sandbox to the bash tool's sandbox config
        if bash_tool._sandbox_config:
            bash_tool._sandbox_config.skip_sandbox = skip_sandbox
        registry.register(bash_tool)

    # Register file tools with sandbox config
    if "Read" not in disabled_tools:
        registry.register(file.FileReadTool(
            base_dir=project_root,
            sandbox_config=sandbox_config,
        ))
    if "Write" not in disabled_tools:
        registry.register(file.FileWriteTool(
            base_dir=project_root,
            sandbox_config=sandbox_config,
        ))
    if "Edit" not in disabled_tools:
        registry.register(file.FileEditTool(
            base_dir=project_root,
            sandbox_config=sandbox_config,
        ))

    # Register search tools with sandbox config
    if "Grep" not in disabled_tools:
        registry.register(grep.GrepTool(
            base_dir=project_root,
            sandbox_config=sandbox_config,
        ))
    if "Glob" not in disabled_tools:
        registry.register(glob_tool.GlobTool(
            base_dir=project_root,
            sandbox_config=sandbox_config,
        ))

    # Register inspect tool (read-only, no permission required)
    if "Inspect" not in disabled_tools:
        registry.register(inspect_tool.InspectTool(
            working_dir=project_root,
            sandbox_config=sandbox_config,
        ))

    return registry


# Builtin tool names for reference
BUILTIN_TOOL_NAMES = frozenset({"Bash", "Read", "Write", "Edit", "Grep", "Glob", "Inspect"})

