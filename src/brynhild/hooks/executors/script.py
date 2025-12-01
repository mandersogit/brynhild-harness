"""
Script hook executor - runs Python scripts with JSON I/O.

Script hooks receive context as JSON on stdin and output their
result as JSON on stdout. This allows more complex hook logic
than command hooks.

Example script:
    import json
    import sys

    context = json.load(sys.stdin)
    # ... process context ...
    json.dump({"action": "continue"}, sys.stdout)
"""

from __future__ import annotations

import asyncio as _asyncio
import json as _json
import pathlib as _pathlib

import brynhild.hooks.config as config
import brynhild.hooks.events as events
import brynhild.hooks.executors.base as base


class ScriptHookExecutor(base.HookExecutor):
    """
    Executor for script hooks.

    Runs Python scripts, passing context as JSON on stdin and
    parsing the result from JSON on stdout.
    """

    @property
    def hook_type(self) -> str:
        return "script"

    async def _execute_impl(
        self,
        hook_def: config.HookDefinition,
        context: events.HookContext,
    ) -> events.HookResult:
        """
        Execute a script hook.

        Runs the script with context JSON on stdin, parses result
        from stdout.
        """
        script_path_str = hook_def.script
        if not script_path_str:
            raise base.HookExecutionError("Script hook has no script path")

        # Resolve script path relative to project root
        script_path = _pathlib.Path(script_path_str)
        if not script_path.is_absolute():
            script_path = self._project_root / script_path

        if not script_path.exists():
            raise base.HookExecutionError(f"Script not found: {script_path}")

        # Prepare context JSON
        context_json = context.to_json()

        # Run script with Python interpreter
        # Use sys.executable equivalent - but we'll use python3 for simplicity
        # In production, could detect the venv Python
        process = await _asyncio.create_subprocess_exec(
            "python3",
            str(script_path),
            stdin=_asyncio.subprocess.PIPE,
            stdout=_asyncio.subprocess.PIPE,
            stderr=_asyncio.subprocess.PIPE,
            cwd=str(context.cwd),
        )

        stdout, stderr = await process.communicate(input=context_json.encode("utf-8"))

        if process.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            raise base.HookExecutionError(
                f"Script '{script_path}' failed (exit {process.returncode}): {error_msg}"
            )

        # Parse result from stdout
        stdout_str = stdout.decode("utf-8", errors="replace").strip()
        if not stdout_str:
            # Empty output = continue
            return events.HookResult.construct_continue()

        try:
            result_data = _json.loads(stdout_str)
            return events.HookResult.from_dict(result_data)
        except _json.JSONDecodeError as e:
            raise base.HookExecutionError(
                f"Script '{script_path}' returned invalid JSON: {e}"
            ) from e

