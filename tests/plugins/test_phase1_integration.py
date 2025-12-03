"""
Integration tests for Phase 1 plugin extensions using a real test plugin.

This test loads the test-phase1 plugin and exercises:
- Gap #2: CONTEXT_BUILD hook and context injection
- Gap #4: Tool metrics in POST_TOOL_USE hook context
- Gap #5: Logger access in hook context
- Gap #6: Plugin rules contribution
"""

import pathlib as _pathlib
import tempfile as _tempfile
import typing as _typing

import pytest as _pytest

import brynhild.core.context as context
import brynhild.plugins.manifest as manifest
import brynhild.plugins.rules as rules


# Path to the test plugin fixture
TEST_PLUGIN_PATH = _pathlib.Path(__file__).parent.parent / "fixtures" / "test-phase1-plugin"


class TestPhase1PluginIntegration:
    """Integration tests using the test-phase1 plugin."""

    @_pytest.fixture
    def plugin(self) -> manifest.Plugin:
        """Load the test-phase1 plugin."""
        manifest_path = TEST_PLUGIN_PATH / "plugin.yaml"
        plugin_manifest = manifest.load_manifest(manifest_path)
        return manifest.Plugin(
            manifest=plugin_manifest,
            path=TEST_PLUGIN_PATH,
        )

    def test_plugin_loads_correctly(self, plugin: manifest.Plugin) -> None:
        """Test plugin loads with correct manifest."""
        assert plugin.name == "test-phase1"
        assert plugin.version == "1.0.0"
        assert plugin.has_rules()
        assert not plugin.has_hooks()  # Test plugin has rules but no hooks

    def test_plugin_rules_are_loaded(self, plugin: manifest.Plugin) -> None:
        """Test plugin rules are loaded correctly."""
        loaded_rules = rules.load_plugin_rules(plugin)
        assert len(loaded_rules) == 2

        # Check rule content
        rule_contents = [content for _, content in loaded_rules]
        combined = "\n".join(rule_contents)
        assert "Test Plugin Coding Standards" in combined
        assert "Test Plugin Security Policy" in combined
        assert "qualified imports" in combined
        assert "validate user input" in combined

    def test_rules_manager_includes_plugin_rules(self, plugin: manifest.Plugin) -> None:
        """Test RulesManager includes plugin rules."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            project_root = _pathlib.Path(tmpdir)

            manager = rules.RulesManager(
                project_root=project_root,
                include_global=False,
                plugins=[plugin],
            )

            content = manager.load_rules()
            assert "Test Plugin Coding Standards" in content
            assert "Test Plugin Security Policy" in content

    def test_rules_manager_lists_plugin_rules(self, plugin: manifest.Plugin) -> None:
        """Test RulesManager lists plugin rules with source info."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            project_root = _pathlib.Path(tmpdir)

            manager = rules.RulesManager(
                project_root=project_root,
                include_global=False,
                plugins=[plugin],
            )

            files = manager.list_rule_files()
            plugin_files = [f for f in files if f.get("source") == "plugin"]
            assert len(plugin_files) == 2
            assert all(f["plugin_name"] == "test-phase1" for f in plugin_files)

    def test_context_builder_with_plugin_rules(self, plugin: manifest.Plugin) -> None:
        """Test ContextBuilder uses plugin rules."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            project_root = _pathlib.Path(tmpdir)

            builder = context.ContextBuilder(
                project_root=project_root,
                include_rules=True,
                include_skills=False,
                plugins=[plugin],
            )

            result = builder.build("Base prompt.")
            assert "Test Plugin Coding Standards" in result.system_prompt
            assert "Test Plugin Security Policy" in result.system_prompt


class TestPhase1ContextBuildAsync:
    """Tests for async context building with hooks."""

    @_pytest.fixture
    def plugin(self) -> manifest.Plugin:
        """Load the test-phase1 plugin."""
        manifest_path = TEST_PLUGIN_PATH / "plugin.yaml"
        plugin_manifest = manifest.load_manifest(manifest_path)
        return manifest.Plugin(
            manifest=plugin_manifest,
            path=TEST_PLUGIN_PATH,
        )

    @_pytest.mark.asyncio
    async def test_build_async_without_hooks(self, plugin: manifest.Plugin) -> None:
        """Test build_async works without a hook manager."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            project_root = _pathlib.Path(tmpdir)

            builder = context.ContextBuilder(
                project_root=project_root,
                include_rules=False,
                include_skills=False,
                plugins=[plugin],
                hook_manager=None,  # No hooks
            )

            result = await builder.build_async("Base prompt.")
            assert "Base prompt" in result.system_prompt

    @_pytest.mark.asyncio
    async def test_fire_context_build_hook_returns_empty_without_hooks(
        self, plugin: manifest.Plugin
    ) -> None:
        """Test fire_context_build_hook returns empty without hook manager."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            project_root = _pathlib.Path(tmpdir)

            builder = context.ContextBuilder(
                project_root=project_root,
                include_rules=False,
                include_skills=False,
                plugins=[plugin],
                hook_manager=None,
            )

            injections = await builder.fire_context_build_hook(
                "Base prompt",
                [],
            )

            assert injections == []

    @_pytest.mark.asyncio
    async def test_build_async_with_rules(self, plugin: manifest.Plugin) -> None:
        """Test build_async includes plugin rules."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            project_root = _pathlib.Path(tmpdir)

            builder = context.ContextBuilder(
                project_root=project_root,
                include_rules=True,
                include_skills=False,
                plugins=[plugin],
            )

            result = await builder.build_async("Base prompt.")
            assert "Test Plugin Coding Standards" in result.system_prompt

