"""
Custom tool loading from plugin directories and entry points.

Tools are Python modules in a plugin's tools/ directory that define
a Tool class implementing the Tool interface. Tools can also be
registered directly via the 'brynhild.tools' entry point group.
"""

from __future__ import annotations

import importlib.metadata as _meta
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
    """
    Check if an object is a valid Tool class.

    Valid tools must either:
    1. Inherit from Tool (has _is_brynhild_duck_typed = False), or
    2. Explicitly declare _is_brynhild_duck_typed = True and implement interface

    Returns False for classes without _is_brynhild_duck_typed attribute.
    Logs a warning if the class looks like a tool but is missing the marker.
    """
    if not isinstance(obj, type):
        return False

    # Must have the _is_brynhild_duck_typed marker (None means not present)
    is_duck_typed = getattr(obj, "_is_brynhild_duck_typed", None)
    if is_duck_typed is None:
        # Check if this looks like a tool (has tool-like attributes)
        # If so, warn the user - they probably forgot the marker
        has_name = hasattr(obj, "name")
        has_execute = callable(getattr(obj, "execute", None))
        has_run = callable(getattr(obj, "run", None))

        if has_name and (has_execute or has_run):
            _logger.warning(
                "=" * 70 + "\n"
                "TOOL NOT RECOGNIZED: %s\n"
                "\n"
                "This class has tool-like attributes (name, execute/run)\n"
                "but is missing the required '_is_brynhild_duck_typed' marker.\n"
                "\n"
                "To fix, either:\n"
                "  1. Inherit from brynhild.tools.base.Tool (recommended), or\n"
                "  2. Add: _is_brynhild_duck_typed = True\n"
                "\n" + "=" * 70,
                obj.__name__,
            )
        return False

    if is_duck_typed:
        # Duck-typed: validate interface manually
        return hasattr(obj, "name") and (
            callable(getattr(obj, "execute", None))
            or callable(getattr(obj, "run", None))
        )
    else:
        # Inherited from Tool: trust the base class contract
        return True


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


def _entry_points_disabled() -> bool:
    """Check if entry point plugin discovery is disabled."""
    import os as _os
    return _os.environ.get("BRYNHILD_DISABLE_ENTRY_POINT_PLUGINS", "").lower() in (
        "1", "true", "yes"
    )


def discover_tools_from_entry_points() -> dict[str, ToolClass]:
    """
    Discover individual tools registered via entry points.

    These are tools registered without a full plugin manifest,
    using the 'brynhild.tools' entry point group. This is useful
    for simple single-tool packages.

    Entry point format in pyproject.toml:
        [project.entry-points."brynhild.tools"]
        MyTool = "my_package.tools:MyTool"

    Can be disabled by setting BRYNHILD_DISABLE_ENTRY_POINT_PLUGINS=1.

    Returns:
        Dict mapping tool name to Tool class.
    """
    if _entry_points_disabled():
        _logger.debug("Entry point tool discovery disabled by environment variable")
        return {}

    tools: dict[str, ToolClass] = {}

    # Python 3.10+ supports the group= keyword argument
    eps = _meta.entry_points(group="brynhild.tools")

    for ep in eps:
        try:
            tool_cls = ep.load()

            if not _is_tool_class(tool_cls):
                _logger.warning(
                    "Entry point '%s' is not a valid Tool class "
                    "(must have 'name' attribute and 'execute' method)",
                    ep.name,
                )
                continue

            tool_name = _get_tool_name(tool_cls, ep.name)
            tools[tool_name] = tool_cls

            _logger.debug(
                "Discovered tool '%s' from entry point '%s' (package: %s)",
                tool_name,
                ep.name,
                getattr(ep.dist, "name", "unknown") if ep.dist else "unknown",
            )
        except Exception as e:
            _logger.warning(
                "Failed to load tool from entry point '%s': %s",
                ep.name,
                e,
            )

    return tools

