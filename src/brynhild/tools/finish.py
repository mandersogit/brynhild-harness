"""
Finish tool for explicit task completion signaling.

This tool allows the agent to explicitly signal when a task is complete,
providing structured completion status and summary information.
"""

from __future__ import annotations

import typing as _typing

import brynhild.tools.base as base


class FinishTool(base.Tool):
    """
    Signal explicit task completion.

    Use this tool when you have completed the user's request,
    or when you cannot proceed further. This provides clear
    signaling of task status rather than implicit completion.
    """

    @property
    def name(self) -> str:
        return "Finish"

    @property
    def description(self) -> str:
        return (
            "Signal that you have finished working on the task. "
            "Use this to explicitly indicate completion status and provide a summary. "
            "Statuses: 'success' (task done), 'partial' (some progress made), "
            "'failed' (could not complete), 'blocked' (need user input to proceed)."
        )

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def categories(self) -> list[str]:
        return ["control", "lifecycle"]

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["success", "partial", "failed", "blocked"],
                    "description": (
                        "Completion status: "
                        "'success' - task completed successfully, "
                        "'partial' - made progress but not fully complete, "
                        "'failed' - could not complete the task, "
                        "'blocked' - need user input or action to proceed"
                    ),
                },
                "summary": {
                    "type": "string",
                    "description": "Summary of what was accomplished or why incomplete",
                },
                "next_steps": {
                    "type": "string",
                    "description": "Optional suggestions for the user's next actions",
                },
            },
            "required": ["status", "summary"],
        }

    @property
    def requires_permission(self) -> bool:
        return False  # No side effects - just signals completion

    @property
    def risk_level(self) -> base.RiskLevel:
        return "read_only"  # Control flow only, no external effects

    async def execute(self, input: dict[str, _typing.Any]) -> base.ToolResult:
        """Execute the finish signal.

        The actual finish handling is done by ConversationProcessor,
        but this returns a confirmation for logging/display purposes.
        """
        status = input.get("status", "success")
        summary = input.get("summary", "Task completed.")
        next_steps = input.get("next_steps")

        output_lines = [
            f"Status: {status}",
            f"Summary: {summary}",
        ]
        if next_steps:
            output_lines.append(f"Next steps: {next_steps}")

        return base.ToolResult(
            success=True,
            output="\n".join(output_lines),
        )

