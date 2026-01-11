"""
Test commands for entry point discovery integration tests.

Demonstrates commands registration via 'brynhild.commands' entry point.
"""

from __future__ import annotations

import pathlib as _pathlib


def get_command():
    """
    Get the command for this plugin.

    Called automatically when Brynhild discovers commands via the
    'brynhild.commands' entry point.

    Returns:
        A Command instance, or a dict with 'name' and 'body' keys.
    """
    # Import here to avoid circular imports during discovery
    import brynhild.plugins.commands as commands_module

    return commands_module.Command(
        frontmatter=commands_module.CommandFrontmatter(
            name="test-cmd",
            description="A test slash command from an entry point plugin",
            aliases=["tc", "testcmd"],
            args="<message>",
        ),
        body="""
# Test Command from Entry Point Plugin

This command was loaded via the `brynhild.commands` entry point.

User's message: {{args}}

Current working directory: {{cwd}}

Please respond to the user's message above, acknowledging that you received it
through the test command.
""".strip(),
        path=_pathlib.Path("<entry-point>"),
        plugin_name="test-complete",
    )


def get_command_as_dict():
    """
    Alternative: Get command as a raw dict.

    This demonstrates that commands can also be provided as dicts
    with the required keys.
    """
    return {
        "name": "test-cmd-dict",
        "description": "A test command provided as a dict",
        "aliases": ["tcd"],
        "args": "<text>",
        "body": "Process this text: {{args}}",
    }

