"""
Command hook executor - runs shell commands.

Command hooks execute shell commands and use exit codes to determine
the result:
- Exit 0: CONTINUE (proceed normally)
- Exit non-zero: BLOCK (stop operation)

Environment variables are injected with hook context (BRYNHILD_*).
"""

from __future__ import annotations

import asyncio as _asyncio
import os as _os

import brynhild.hooks.config as config
import brynhild.hooks.events as events
import brynhild.hooks.executors.base as base


class CommandHookExecutor(base.HookExecutor):
    """
    Executor for command hooks.

    Runs shell commands via subprocess, injecting context as environment
    variables. Uses exit code to determine result.
    """

    @property
    def hook_type(self) -> str:
        return "command"

    async def _execute_impl(
        self,
        hook_def: config.HookDefinition,
        context: events.HookContext,
    ) -> events.HookResult:
        """
        Execute a command hook.

        Runs the command in a subprocess with BRYNHILD_* environment
        variables set from the context.
        """
        command = hook_def.command
        if not command:
            raise base.HookExecutionError("Command hook has no command")

        # Build environment with context
        env = _os.environ.copy()
        env.update(context.to_env_vars())

        # Run command
        process = await _asyncio.create_subprocess_shell(
            command,
            stdout=_asyncio.subprocess.PIPE,
            stderr=_asyncio.subprocess.PIPE,
            cwd=str(context.cwd),
            env=env,
        )

        stdout, stderr = await process.communicate()

        # Determine result from exit code
        if process.returncode == 0:
            return events.HookResult.continue_()
        else:
            # Non-zero exit = block
            message = hook_def.message
            if not message:
                # Use stderr or stdout as message
                output = stderr.decode("utf-8", errors="replace").strip()
                if not output:
                    output = stdout.decode("utf-8", errors="replace").strip()
                message = output or f"Hook '{hook_def.name}' blocked (exit {process.returncode})"

            return events.HookResult.block(message)

