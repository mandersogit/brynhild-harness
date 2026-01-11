"""
Comprehensive test plugin for entry point discovery integration tests.

This plugin demonstrates and tests ALL plugin features via entry points:
- Plugin manifest registration (brynhild.plugins)
- Tool registration (brynhild.tools)
- Provider registration (brynhild.providers)
- Hooks registration (brynhild.hooks)
- Skills registration (brynhild.skills)
- Commands registration (brynhild.commands)
- Rules registration (brynhild.rules)
"""

from __future__ import annotations


def register():
    """
    Register this plugin with Brynhild.

    Called automatically when Brynhild discovers this plugin via the
    'brynhild.plugins' entry point.

    Returns:
        PluginManifest describing the plugin.
    """
    # Import here to avoid circular imports during discovery
    import brynhild.plugins.manifest as manifest

    return manifest.PluginManifest(
        name="test-complete",
        version="0.0.1",
        description="Comprehensive test plugin for all entry point features",
        # Declare tools that are registered via brynhild.tools entry point
        tools=["TestEcho", "TestCounter"],
        # Declare that we provide hooks
        hooks=True,
        # Declare skills
        skills=["test-skill"],
        # Declare that we provide providers
        providers=["test-mock"],
        # Declare that we have commands
        commands=["test-cmd"],
        # Declare that we have rules
        rules=["test-rules"],
    )

