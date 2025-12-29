"""
Plugin lifecycle management.

Handles firing PLUGIN_INIT and PLUGIN_SHUTDOWN hooks at appropriate times
in the plugin lifecycle.

Plugins can respond to these hooks by defining handlers in their hooks.yaml:

    plugin_init:
      - name: initialize_connections
        type: command
        command: ./scripts/init.sh

    plugin_shutdown:
      - name: cleanup_resources
        type: command
        command: ./scripts/cleanup.sh
"""

from __future__ import annotations

import asyncio as _asyncio
import atexit as _atexit
import logging as _logging
import pathlib as _pathlib
import typing as _typing
import uuid as _uuid

if _typing.TYPE_CHECKING:
    import brynhild.plugins.manifest as _manifest

_logger = _logging.getLogger(__name__)

# Track initialized plugins for shutdown
_initialized_plugins: list[tuple[str, _pathlib.Path]] = []
_shutdown_registered: bool = False


async def fire_plugin_init(
    plugin: _manifest.Plugin,
    *,
    project_root: _pathlib.Path | None = None,
) -> None:
    """
    Fire PLUGIN_INIT hook for a plugin.

    Called after a plugin is fully loaded and its components are registered.

    Args:
        plugin: The plugin that was initialized.
        project_root: Project root directory.
    """
    import brynhild.hooks.events as events
    import brynhild.hooks.manager as hooks_manager
    import brynhild.plugins.hooks as plugin_hooks

    global _shutdown_registered

    # Create hook manager with plugin's hooks merged
    try:
        hooks_config = plugin_hooks.load_plugin_hooks(plugin)
        if hooks_config is None:
            # Plugin has no hooks defined
            _logger.debug("Plugin %s has no hooks defined", plugin.name)
            _track_plugin_for_shutdown(plugin)
            return

        manager = hooks_manager.HookManager(hooks_config, project_root=project_root)
    except Exception as e:
        _logger.warning("Failed to load hooks for plugin %s: %s", plugin.name, e)
        _track_plugin_for_shutdown(plugin)
        return

    # Check if any PLUGIN_INIT hooks are defined
    if not manager.has_hooks_for_event(events.HookEvent.PLUGIN_INIT):
        _logger.debug("Plugin %s has no plugin_init hooks", plugin.name)
        _track_plugin_for_shutdown(plugin)
        return

    # Fire the hook
    context = events.HookContext(
        event=events.HookEvent.PLUGIN_INIT,
        session_id=_uuid.uuid4().hex[:16],  # Lifecycle events don't have a real session
        cwd=project_root or _pathlib.Path.cwd(),
        plugin_name=plugin.name,
        plugin_path=plugin.path,
    )

    try:
        _logger.debug("Firing plugin_init for %s", plugin.name)
        result = await manager.dispatch(events.HookEvent.PLUGIN_INIT, context)
        _logger.debug("Plugin %s init hook result: %s", plugin.name, result.action.value)
    except Exception as e:
        _logger.warning("Plugin %s init hook failed: %s", plugin.name, e)

    _track_plugin_for_shutdown(plugin)


def _track_plugin_for_shutdown(plugin: _manifest.Plugin) -> None:
    """Track a plugin for shutdown hooks."""
    global _shutdown_registered

    _initialized_plugins.append((plugin.name, plugin.path))

    # Register shutdown handler once
    if not _shutdown_registered:
        _atexit.register(_run_shutdown_hooks)
        _shutdown_registered = True


def _run_shutdown_hooks() -> None:
    """Run shutdown hooks for all initialized plugins (called via atexit)."""
    if not _initialized_plugins:
        return

    _logger.debug("Running shutdown hooks for %d plugins", len(_initialized_plugins))

    # Create event loop if needed (atexit may run outside async context)
    try:
        loop = _asyncio.get_running_loop()
    except RuntimeError:
        loop = _asyncio.new_event_loop()
        _asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(_fire_all_shutdown_hooks())
    except Exception as e:
        _logger.warning("Error running shutdown hooks: %s", e)
    finally:
        if not _asyncio.get_event_loop().is_running():
            loop.close()


async def _fire_all_shutdown_hooks() -> None:
    """Fire PLUGIN_SHUTDOWN for all tracked plugins."""
    import brynhild.hooks.events as events
    import brynhild.hooks.manager as hooks_manager
    import brynhild.plugins.hooks as plugin_hooks
    import brynhild.plugins.loader as loader

    plugin_loader = loader.PluginLoader()

    for plugin_name, plugin_path in _initialized_plugins:
        try:
            # Check if plugin directory still exists (may be temp dir from tests)
            if not plugin_path.exists():
                _logger.debug("Plugin %s path no longer exists, skipping shutdown", plugin_name)
                continue

            # Reload plugin to get hooks config
            plugin = plugin_loader.load(plugin_path)
            hooks_config = plugin_hooks.load_plugin_hooks(plugin)

            if hooks_config is None:
                continue

            manager = hooks_manager.HookManager(hooks_config, project_root=plugin_path.parent)

            if not manager.has_hooks_for_event(events.HookEvent.PLUGIN_SHUTDOWN):
                continue

            context = events.HookContext(
                event=events.HookEvent.PLUGIN_SHUTDOWN,
                session_id=_uuid.uuid4().hex[:16],
                cwd=plugin_path.parent,
                plugin_name=plugin_name,
                plugin_path=plugin_path,
            )

            _logger.debug("Firing plugin_shutdown for %s", plugin_name)
            await manager.dispatch(events.HookEvent.PLUGIN_SHUTDOWN, context)

        except Exception as e:
            _logger.debug("Plugin %s shutdown hook skipped: %s", plugin_name, e)


async def fire_plugin_init_for_all(
    plugins: list[_manifest.Plugin],
    *,
    project_root: _pathlib.Path | None = None,
) -> None:
    """
    Fire PLUGIN_INIT hooks for all provided plugins.

    Args:
        plugins: List of plugins to initialize.
        project_root: Project root directory.
    """
    for plugin in plugins:
        if plugin.enabled:
            await fire_plugin_init(plugin, project_root=project_root)


def fire_plugin_init_sync(
    plugin: _manifest.Plugin,
    *,
    project_root: _pathlib.Path | None = None,
) -> None:
    """
    Synchronous wrapper for fire_plugin_init.

    Creates an event loop if needed.

    Args:
        plugin: The plugin that was initialized.
        project_root: Project root directory.
    """
    try:
        _asyncio.get_running_loop()
        # Already in async context - caller should use async version directly.
        # Creating a fire-and-forget task causes orphaned tasks that block teardown.
        _logger.debug("Skipping sync lifecycle hooks - already in async context")
        return
    except RuntimeError:
        # No event loop - safe to create one
        _asyncio.run(fire_plugin_init(plugin, project_root=project_root))


def fire_plugin_init_for_all_sync(
    plugins: list[_manifest.Plugin],
    *,
    project_root: _pathlib.Path | None = None,
) -> None:
    """
    Synchronous wrapper for fire_plugin_init_for_all.

    Args:
        plugins: List of plugins to initialize.
        project_root: Project root directory.
    
    Note:
        When called from an async context (e.g., pytest-asyncio), this skips
        hook firing to avoid orphaned tasks that cause 30s teardown delays.
        Callers in async contexts should use fire_plugin_init_for_all() directly.
    """
    try:
        _asyncio.get_running_loop()
        # Already in async context - caller should use async version directly.
        # Creating a fire-and-forget task here causes orphaned tasks that block
        # event loop teardown for 30 seconds (the default hook timeout).
        _logger.debug("Skipping sync lifecycle hooks - already in async context")
        return
    except RuntimeError:
        # No event loop - safe to create one
        _asyncio.run(fire_plugin_init_for_all(plugins, project_root=project_root))

