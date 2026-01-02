"""
Test plugin for entry point discovery integration tests.

This plugin demonstrates the correct way to create a pip-installable
Brynhild plugin that provides tools.
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
        name="test-plugin",
        version="0.0.1",
        description="Test plugin for entry point discovery",
        tools=["TestCalculator"],  # Declared tools
    )
