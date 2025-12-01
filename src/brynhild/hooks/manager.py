"""
Hook manager - central coordinator for hook execution.

The HookManager loads hook configuration and dispatches events to hooks
in the correct order, handling results and modifications.
"""

from __future__ import annotations

import logging as _logging
import pathlib as _pathlib
import typing as _typing

import brynhild.hooks.config as config
import brynhild.hooks.events as events
import brynhild.hooks.matching as matching

if _typing.TYPE_CHECKING:
    import brynhild.hooks.executors.base as executors_base

_logger = _logging.getLogger(__name__)


class HookManager:
    """
    Central manager for hook execution.

    Loads hook configuration, matches events to hooks, and executes
    hooks in order. Handles blocking, modifications, and error recovery.

    Hooks are executed sequentially in definition order. If any hook
    returns BLOCK, execution stops and the block result is returned.
    Modifications from earlier hooks are visible to later hooks.
    """

    def __init__(
        self,
        hooks_config: config.HooksConfig,
        *,
        project_root: _pathlib.Path | None = None,
    ) -> None:
        """
        Initialize the hook manager.

        Args:
            hooks_config: Loaded hooks configuration.
            project_root: Project root directory (for resolving script paths).
        """
        self._config = hooks_config
        self._project_root = project_root or _pathlib.Path.cwd()
        self._executors: dict[str, executors_base.HookExecutor] = {}

    @classmethod
    def from_config(
        cls,
        project_root: _pathlib.Path | None = None,
    ) -> HookManager:
        """
        Create a HookManager by loading configuration files.

        Loads and merges global (~/.config/brynhild/hooks.yaml) and
        project (.brynhild/hooks.yaml) configurations.

        Args:
            project_root: Project root directory.

        Returns:
            Configured HookManager.
        """
        hooks_config = config.load_merged_config(project_root)
        return cls(hooks_config, project_root=project_root)

    @classmethod
    def empty(cls) -> HookManager:
        """Create a HookManager with no hooks configured."""
        return cls(config.HooksConfig())

    async def dispatch(
        self,
        event: events.HookEvent,
        context: events.HookContext,
    ) -> events.HookResult:
        """
        Dispatch an event to all matching hooks.

        Hooks are executed sequentially. If any hook returns BLOCK,
        execution stops immediately. Modifications accumulate.

        Args:
            event: The event being dispatched.
            context: Context for the event.

        Returns:
            Combined result from all hooks. If any hook blocked,
            returns that block result. Otherwise returns CONTINUE
            with any accumulated modifications.
        """
        hooks = self._config.get_hooks_for_event(event)
        if not hooks:
            return events.HookResult.continue_()

        context_dict = context.to_dict()
        accumulated_result = events.HookResult.continue_()

        for hook_def in hooks:
            # Check if hook matches
            if not self._matches_hook(hook_def, context_dict):
                continue

            # Execute the hook
            try:
                result = await self._execute_hook(hook_def, context)
            except Exception as e:
                _logger.warning(
                    "Hook %s failed with error: %s",
                    hook_def.name,
                    e,
                )
                # Hook errors don't block by default - continue
                continue

            # Handle the result
            if result.action == events.HookAction.BLOCK:
                # Blocking hook stops execution immediately
                if not event.can_block:
                    _logger.warning(
                        "Hook %s tried to block event %s which cannot be blocked",
                        hook_def.name,
                        event.value,
                    )
                    continue
                return result

            if result.action == events.HookAction.SKIP:
                # Skip action also stops execution
                return result

            # Accumulate modifications
            if event.can_modify:
                accumulated_result = self._merge_modifications(
                    accumulated_result,
                    result,
                )

                # Update context_dict with modifications for subsequent hooks
                if result.modified_input is not None:
                    context_dict["tool_input"] = result.modified_input
                if result.modified_output is not None:
                    context_dict["tool_result"] = {
                        **context_dict.get("tool_result", {}),
                        "output": result.modified_output,
                    }
                if result.modified_message is not None:
                    context_dict["message"] = result.modified_message
                if result.modified_response is not None:
                    context_dict["response"] = result.modified_response

        return accumulated_result

    def _matches_hook(
        self,
        hook_def: config.HookDefinition,
        context_dict: dict[str, _typing.Any],
    ) -> bool:
        """Check if a hook's match conditions are satisfied."""
        if not hook_def.match:
            return True
        return matching.match_patterns(hook_def.match, context_dict)

    async def _execute_hook(
        self,
        hook_def: config.HookDefinition,
        context: events.HookContext,
    ) -> events.HookResult:
        """
        Execute a single hook.

        Gets or creates the appropriate executor and runs the hook.
        """
        executor = self._get_executor(hook_def)
        return await executor.execute(hook_def, context)

    def _get_executor(
        self,
        hook_def: config.HookDefinition,
    ) -> executors_base.HookExecutor:
        """Get or create an executor for the hook type."""
        # Import here to avoid circular imports
        import brynhild.hooks.executors as executors

        hook_type = hook_def.type
        if hook_type not in self._executors:
            self._executors[hook_type] = executors.create_executor(
                hook_type,
                project_root=self._project_root,
            )
        return self._executors[hook_type]

    def _merge_modifications(
        self,
        accumulated: events.HookResult,
        new: events.HookResult,
    ) -> events.HookResult:
        """Merge modifications from a new result into the accumulated result."""
        return events.HookResult(
            action=events.HookAction.CONTINUE,
            message=new.message or accumulated.message,
            modified_input=new.modified_input or accumulated.modified_input,
            modified_output=new.modified_output or accumulated.modified_output,
            modified_message=new.modified_message or accumulated.modified_message,
            modified_response=new.modified_response or accumulated.modified_response,
            inject_system_message=(
                new.inject_system_message or accumulated.inject_system_message
            ),
        )

    def get_hooks_for_event(self, event: events.HookEvent) -> list[config.HookDefinition]:
        """Get all hooks configured for an event (for inspection/debugging)."""
        return self._config.get_hooks_for_event(event)

    def has_hooks_for_event(self, event: events.HookEvent) -> bool:
        """Check if any hooks are configured for an event."""
        return len(self._config.get_hooks_for_event(event)) > 0

