"""
Brynhild Entry-Point Plugin Template

This module demonstrates the correct way to create a pip-installable
Brynhild plugin. Rename 'brynhild_my_plugin' to your package name.
"""

import brynhild.plugins.manifest as manifest


def get_manifest() -> manifest.PluginManifest:
    """
    Return the plugin manifest.

    This function is called by Brynhild to get plugin metadata.
    Registered via: brynhild.plugins entry point

    Returns:
        PluginManifest with plugin metadata.

    Note:
        The 'tools' and 'providers' lists here are for documentation only.
        For entry-point plugins, tools and providers MUST also be registered
        via brynhild.tools and brynhild.providers entry points.
    """
    return manifest.PluginManifest(
        name="my-plugin",
        version="0.1.0",
        description="Example plugin demonstrating all Brynhild features",
        # These list your tools/providers for documentation,
        # but brynhild.tools entry points are required for discovery
        tools=["greeter", "counter"],
        providers=[],
        # Declare additional features
        skills=["my-skill"],
        hooks=["pre_tool_use", "post_tool_use"],
        commands=["my-command"],
    )


# You can also return a dict instead of PluginManifest:
#
# def get_manifest():
#     return {
#         "name": "my-plugin",
#         "version": "0.1.0",
#         "description": "Example plugin",
#         "tools": ["greeter"],
#     }

