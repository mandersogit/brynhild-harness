"""
Test hooks for entry point discovery integration tests.

Demonstrates hooks registration via 'brynhild.hooks' entry point.
"""

from __future__ import annotations


def get_hooks():
    """
    Get the hooks configuration for this plugin.

    Called automatically when Brynhild discovers hooks via the
    'brynhild.hooks' entry point.

    Returns:
        A dict that validates as HooksConfig, or a HooksConfig instance.
    """
    # Import here to avoid circular imports during discovery
    import brynhild.hooks.config as hooks_config

    return hooks_config.HooksConfig(
        hooks={
            "pre_tool_use": [
                hooks_config.HookDefinition(
                    name="test-pre-hook",
                    type="command",
                    command="echo 'Test pre-tool hook from entry point plugin'",
                    enabled=True,
                    timeout=hooks_config.HookTimeoutConfig(seconds=5),
                ),
            ],
            "post_tool_use": [
                hooks_config.HookDefinition(
                    name="test-post-hook",
                    type="command",
                    command="echo 'Test post-tool hook from entry point plugin'",
                    enabled=True,
                    timeout=hooks_config.HookTimeoutConfig(seconds=5),
                ),
            ],
        }
    )


def get_hooks_as_dict():
    """
    Alternative: Get hooks as a raw dict.

    This demonstrates that hooks can also be provided as dicts
    that match the HooksConfig schema.
    """
    return {
        "hooks": {
            "pre_tool_use": [
                {
                    "name": "test-pre-hook-dict",
                    "type": "command",
                    "command": "echo 'Test pre-tool hook from dict'",
                    "enabled": True,
                    "timeout": {"seconds": 5},
                },
            ],
        }
    }

