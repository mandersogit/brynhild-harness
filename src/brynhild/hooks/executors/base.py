"""
Base class for hook executors.

All executors implement the same interface with timeout support.
"""

from __future__ import annotations

import abc as _abc
import asyncio as _asyncio
import pathlib as _pathlib

import brynhild.hooks.config as config
import brynhild.hooks.events as events


class HookExecutor(_abc.ABC):
    """
    Abstract base class for hook executors.

    Executors are responsible for running hooks and returning results.
    All executors support timeout enforcement.
    """

    def __init__(
        self,
        *,
        project_root: _pathlib.Path | None = None,
    ) -> None:
        """
        Initialize the executor.

        Args:
            project_root: Project root directory for resolving paths.
        """
        self._project_root = project_root or _pathlib.Path.cwd()

    @property
    @_abc.abstractmethod
    def hook_type(self) -> str:
        """The hook type this executor handles."""
        ...

    @_abc.abstractmethod
    async def _execute_impl(
        self,
        hook_def: config.HookDefinition,
        context: events.HookContext,
    ) -> events.HookResult:
        """
        Execute the hook (implementation).

        Subclasses implement this method. Timeout handling is done
        by the base class.

        Args:
            hook_def: The hook definition.
            context: The hook context.

        Returns:
            Hook execution result.
        """
        ...

    async def execute(
        self,
        hook_def: config.HookDefinition,
        context: events.HookContext,
    ) -> events.HookResult:
        """
        Execute a hook with timeout enforcement.

        If the hook exceeds its timeout, returns based on the
        configured on_timeout action (block or continue).

        Args:
            hook_def: The hook definition.
            context: The hook context.

        Returns:
            Hook execution result.
        """
        timeout_seconds = hook_def.timeout.seconds
        on_timeout = hook_def.timeout.on_timeout

        try:
            return await _asyncio.wait_for(
                self._execute_impl(hook_def, context),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            if on_timeout == "block":
                return events.HookResult.block(
                    f"Hook '{hook_def.name}' timed out after {timeout_seconds}s"
                )
            else:
                # on_timeout == "continue"
                return events.HookResult.continue_()
        except Exception as e:
            # Execution errors result in continue (don't block on hook failures)
            # The manager will log the error
            raise HookExecutionError(
                f"Hook '{hook_def.name}' failed: {e}"
            ) from e


class HookExecutionError(Exception):
    """Raised when a hook fails to execute."""

    pass

