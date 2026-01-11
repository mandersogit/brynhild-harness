"""
Example slash command for the plugin template.

Commands are registered in pyproject.toml:

    [project.entry-points."brynhild.commands"]
    my-command = "brynhild_my_plugin.commands:get_command"

The entry point can return:
- A Command instance
- A dict with name, body fields
- A callable that returns either

Commands are invoked in chat with /command-name [args]
"""

import brynhild.plugins.commands as commands


def get_command() -> commands.Command:
    """
    Return the command definition.

    Commands can include template variables:
    - {{args}}: The full argument string after the command
    - {{cwd}}: Current working directory

    Returns:
        Command instance with metadata and template.
    """
    return commands.Command(
        # Command name (invoked as /my-command)
        name="my-command",
        # Description shown in /help
        description="Example command from plugin template",
        # Optional: short aliases (e.g., /mc)
        aliases=["mc", "myc"],
        # Command template - what gets sent to the LLM
        body="""
Please help me with the following request: {{args}}

Context:
- Current directory: {{cwd}}
- This command was invoked via the /my-command slash command
""",
    )


# Alternative: Return a dict instead of Command
#
# def get_command():
#     return {
#         "name": "my-command",
#         "description": "Example command",
#         "aliases": ["mc"],
#         "body": "Please help with: {{args}}",
#     }


# Alternative: Return the Command directly
#
# get_command = commands.Command(
#     name="my-command",
#     description="Example command",
#     body="Template here...",
# )

