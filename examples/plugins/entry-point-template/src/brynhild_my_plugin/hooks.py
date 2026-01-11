"""
Example hooks for the plugin template.

Hooks are registered in pyproject.toml:

    [project.entry-points."brynhild.hooks"]
    my-hooks = "brynhild_my_plugin.hooks:get_hooks"

The entry point can return:
- A HooksConfig instance
- A dict matching the HooksConfig schema
- A callable that returns either

HookDefinition required fields:
- name: Unique identifier
- type: One of "command", "script", or "prompt"
  - For type="command": also provide `command` field
  - For type="script": also provide `script` field
  - For type="prompt": also provide `prompt` field
"""

import brynhild.hooks.config as config


def get_hooks() -> config.HooksConfig:
    """
    Return hooks configuration.

    This defines hooks that run before/after tool execution.
    See docs/plugin-development-guide.md for full hook documentation.

    Returns:
        HooksConfig with hook definitions.
    """
    return config.HooksConfig(
        hooks={
            # Hooks that run before tool execution
            "pre_tool_use": [
                config.HookDefinition(
                    name="log-tool-call",
                    type="command",  # Required: "command", "script", or "prompt"
                    command="echo 'Tool being called: {{tool_name}}'",
                    # Optional: conditions for when this hook runs
                    match={"tool_name": "*"},  # Match all tools
                    # Optional: timeout configuration
                    timeout=config.HookTimeoutConfig(
                        seconds=5,
                        on_timeout="continue",  # or "block"
                    ),
                ),
            ],
            # Hooks that run after tool execution
            "post_tool_use": [
                config.HookDefinition(
                    name="log-tool-result",
                    type="command",
                    command="echo 'Tool {{tool_name}} completed'",
                ),
            ],
        }
    )


# Alternative: Return a dict instead of HooksConfig
#
# def get_hooks():
#     return {
#         "hooks": {
#             "pre_tool_use": [
#                 {
#                     "name": "log-tool-call",
#                     "type": "command",  # Required!
#                     "command": "echo 'Tool: {{tool_name}}'",
#                 }
#             ],
#         }
#     }


# Alternative: Use a script hook
#
# def get_hooks():
#     return config.HooksConfig(
#         hooks={
#             "pre_tool_use": [
#                 config.HookDefinition(
#                     name="custom-validation",
#                     type="script",
#                     script="./scripts/validate_tool.py",
#                 ),
#             ],
#         }
#     )


# Alternative: Use a prompt hook (LLM-based)
#
# def get_hooks():
#     return config.HooksConfig(
#         hooks={
#             "pre_tool_use": [
#                 config.HookDefinition(
#                     name="safety-check",
#                     type="prompt",
#                     prompt="Is this tool call safe? Tool: {{tool_name}}, Input: {{input}}",
#                 ),
#             ],
#         }
#     )

