"""
Custom tool loading from plugin directories.

Tools are Python modules in a plugin's tools/ directory that define
a Tool class implementing the Tool interface.
"""

from __future__ import annotations

import importlib.util as _importlib_util
import logging as _logging
import pathlib as _pathlib
import sys as _sys
import typing as _typing

_logger = _logging.getLogger(__name__)

# Type alias for tool classes - we use Any since plugins may not use our Tool base
ToolClass = type[_typing.Any]


class ToolLoadError(Exception):
    """Raised when a tool fails to load."""

    pass


def load_tool_module(
    tool_path: _pathlib.Path,
    plugin_name: str = "",
) -> _typing.Any:
    """
    Dynamically load a Python module from a file path.

    Args:
        tool_path: Path to the .py file.
        plugin_name: Plugin name (for module naming).

    Returns:
        The loaded module.

    Raises:
        ToolLoadError: If module fails to load.
    """
    if not tool_path.exists():
        raise ToolLoadError(f"Tool file not found: {tool_path}")

    if not tool_path.suffix == ".py":
        raise ToolLoadError(f"Tool file must be .py: {tool_path}")

    # Generate a unique module name
    tool_name = tool_path.stem
    module_name = f"brynhild_plugins.{plugin_name}.tools.{tool_name}"

    try:
        spec = _importlib_util.spec_from_file_location(module_name, tool_path)
        if spec is None or spec.loader is None:
            raise ToolLoadError(f"Cannot load module spec for: {tool_path}")

        module = _importlib_util.module_from_spec(spec)
        _sys.modules[module_name] = module
        spec.loader.exec_module(module)

        return module
    except Exception as e:
        raise ToolLoadError(f"Failed to load tool {tool_path}: {e}") from e


def get_tool_class_from_module(
    module: _typing.Any,
    expected_name: str | None = None,
) -> ToolClass | None:
    """
    Find a Tool class in a loaded module.

    Looks for a class that:
    1. Is named 'Tool' or matches expected_name
    2. Has a 'name' attribute (duck typing check for Tool)

    Args:
        module: The loaded module.
        expected_name: Optional expected tool name.

    Returns:
        The Tool class, or None if not found.
    """
    # First try to find a class named 'Tool'
    if hasattr(module, "Tool"):
        tool_cls = module.Tool
        if _is_tool_class(tool_cls):
            return tool_cls  # type: ignore[no-any-return]

    # Look for any class with a 'name' attribute
    for attr_name in dir(module):
        if attr_name.startswith("_"):
            continue
        attr = getattr(module, attr_name)
        if _is_tool_class(attr) and (
            expected_name is None or getattr(attr, "name", None) == expected_name
        ):
            return attr  # type: ignore[no-any-return]

    return None


def _is_tool_class(obj: _typing.Any) -> bool:
    """Check if an object looks like a Tool class."""
    if not isinstance(obj, type):
        return False

    # Duck typing: must have 'name' class attribute or property
    # and should have an 'execute' method
    return hasattr(obj, "name") and (
        callable(getattr(obj, "execute", None))
        or callable(getattr(obj, "run", None))
    )


def _get_tool_name(tool_cls: ToolClass, fallback: str) -> str:
    """
    Get the name from a tool class.

    Handles both class attributes and @property-based names.

    Args:
        tool_cls: The Tool class.
        fallback: Fallback name if name can't be determined.

    Returns:
        The tool's name.
    """
    # Check if 'name' is a property descriptor
    name_attr = getattr(tool_cls, "name", None)

    if isinstance(name_attr, property):
        # It's a property - need to instantiate to get the value
        try:
            instance = tool_cls()
            return str(instance.name)
        except Exception:
            # If instantiation fails, use fallback
            return fallback
    elif isinstance(name_attr, str):
        # It's a class attribute
        return name_attr
    else:
        # Unknown type, use fallback
        return fallback


class ToolLoader:
    """
    Loads custom tools from plugin directories.

    Tools are Python modules in a plugin's tools/ directory that define
    a Tool class. The Tool class should implement the Tool interface.
    """

    def __init__(self) -> None:
        """Initialize the tool loader."""
        self._loaded_tools: dict[str, ToolClass] = {}

    def load_from_file(
        self,
        tool_path: _pathlib.Path,
        plugin_name: str = "",
    ) -> ToolClass | None:
        """
        Load a single tool from a Python file.

        Args:
            tool_path: Path to the .py file.
            plugin_name: Plugin name.

        Returns:
            The Tool class, or None if not found/invalid.
        """
        try:
            module = load_tool_module(tool_path, plugin_name)
            tool_cls = get_tool_class_from_module(module, tool_path.stem)
            if tool_cls is not None:
                self._loaded_tools[tool_path.stem] = tool_cls
            return tool_cls
        except ToolLoadError as e:
            _logger.warning("Failed to load tool: %s", e)
            return None

    def load_from_directory(
        self,
        tools_dir: _pathlib.Path,
        plugin_name: str = "",
    ) -> dict[str, ToolClass]:
        """
        Load all tools from a directory.

        Args:
            tools_dir: Path to tools/ directory.
            plugin_name: Plugin name.

        Returns:
            Dict mapping tool name to Tool class.
        """
        tools: dict[str, ToolClass] = {}

        if not tools_dir.is_dir():
            return tools

        for py_file in sorted(tools_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue  # Skip __init__.py and private modules

            tool_cls = self.load_from_file(py_file, plugin_name)
            if tool_cls is not None:
                tool_name = _get_tool_name(tool_cls, py_file.stem)
                tools[tool_name] = tool_cls

        return tools

    def load_from_plugin(
        self,
        plugin_path: _pathlib.Path,
        plugin_name: str,
    ) -> dict[str, ToolClass]:
        """
        Load tools from a plugin directory.

        Args:
            plugin_path: Root path of the plugin.
            plugin_name: Plugin name.

        Returns:
            Dict mapping tool name to Tool class.
        """
        tools_dir = plugin_path / "tools"
        return self.load_from_directory(tools_dir, plugin_name)

    def get_loaded_tools(self) -> dict[str, ToolClass]:
        """Get all tools loaded so far."""
        return dict(self._loaded_tools)

