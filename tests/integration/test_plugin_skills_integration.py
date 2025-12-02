"""
Integration tests for plugin-provided skills.

Tests that skills bundled in plugins are properly discovered and
available through the SkillRegistry when plugins are passed.
"""

import pathlib as _pathlib

# Path to fixtures
FIXTURES_DIR = _pathlib.Path(__file__).parent.parent / "fixtures"
PLUGINS_DIR = FIXTURES_DIR / "plugins"
TEST_COMPLETE_PLUGIN = PLUGINS_DIR / "test-complete"


class TestPluginSkillDiscovery:
    """Tests for plugin skill discovery integration."""

    def test_plugin_skills_discovered_via_plugins_parameter(self) -> None:
        """Skills from plugins are discovered when plugins are passed to registry."""
        import brynhild.plugins.loader as loader
        import brynhild.skills as skills

        # Load the test-complete plugin
        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(TEST_COMPLETE_PLUGIN)

        # Create registry with plugin
        registry = skills.SkillRegistry(
            project_root=FIXTURES_DIR,
            plugins=[plugin],
        )

        # Get all skills
        skill_list = registry.list_skills()
        skill_names = {s.name for s in skill_list}

        # Plugin skills should be discovered
        assert "debugging" in skill_names, "debugging skill from plugin not found"
        assert "testing" in skill_names, "testing skill from plugin not found"

    def test_plugin_skill_source_identified_correctly(self) -> None:
        """Plugin skills have correct source identifier."""
        import brynhild.plugins.loader as loader
        import brynhild.skills as skills

        # Load the test-complete plugin
        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(TEST_COMPLETE_PLUGIN)

        # Create registry with plugin
        registry = skills.SkillRegistry(
            project_root=FIXTURES_DIR,
            plugins=[plugin],
        )

        # Get debugging skill
        debugging_skill = registry.get_skill("debugging")
        assert debugging_skill is not None

        # Source should be "plugin:<plugin-name>"
        assert debugging_skill.source == "plugin:test-complete"

    def test_plugin_skill_body_accessible(self) -> None:
        """Plugin skill body is fully accessible via trigger."""
        import brynhild.plugins.loader as loader
        import brynhild.skills as skills

        # Load the test-complete plugin
        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(TEST_COMPLETE_PLUGIN)

        # Create registry with plugin
        registry = skills.SkillRegistry(
            project_root=FIXTURES_DIR,
            plugins=[plugin],
        )

        # Trigger the skill
        triggered = registry.trigger_skill("debugging")

        assert triggered is not None
        assert "[TEST-PLUGIN-SKILL: debugging]" in triggered
        assert "Systematic Debugging Process" in triggered

    def test_plugin_skill_metadata_in_prompt(self) -> None:
        """Plugin skill metadata appears in system prompt metadata."""
        import brynhild.plugins.loader as loader
        import brynhild.skills as skills

        # Load the test-complete plugin
        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(TEST_COMPLETE_PLUGIN)

        # Create registry with plugin
        registry = skills.SkillRegistry(
            project_root=FIXTURES_DIR,
            plugins=[plugin],
        )

        # Get metadata for prompt
        metadata = registry.get_metadata_for_prompt()

        # Plugin skills should appear in metadata
        assert "debugging" in metadata
        assert "testing" in metadata

    def test_plugin_skill_scripts_accessible(self) -> None:
        """Plugin skill with scripts has scripts accessible."""
        import brynhild.plugins.loader as loader
        import brynhild.skills as skills

        # Load the test-complete plugin
        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(TEST_COMPLETE_PLUGIN)

        # Create registry with plugin
        registry = skills.SkillRegistry(
            project_root=FIXTURES_DIR,
            plugins=[plugin],
        )

        # Get testing skill (has scripts)
        testing_skill = registry.get_skill("testing")
        assert testing_skill is not None

        # Scripts should be accessible
        scripts = testing_skill.list_scripts()
        script_names = {s.name for s in scripts}
        assert "run_tests.sh" in script_names

    def test_plugin_skills_combined_with_other_sources(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """Plugin skills combine with project and global skills."""
        import brynhild.plugins.loader as loader
        import brynhild.skills as skills

        # Load the test-complete plugin
        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(TEST_COMPLETE_PLUGIN)

        # Create a project skill
        project_skills = tmp_path / ".brynhild" / "skills" / "project-skill"
        project_skills.mkdir(parents=True)
        (project_skills / "SKILL.md").write_text("""---
name: project-skill
description: A project-local skill
---

Project skill body.
""")

        # Create registry with plugin AND project root
        registry = skills.SkillRegistry(
            project_root=tmp_path,
            plugins=[plugin],
        )

        # Get all skills
        skill_list = registry.list_skills()
        skill_names = {s.name for s in skill_list}

        # Both plugin and project skills should be found
        assert "debugging" in skill_names, "plugin skill not found"
        assert "testing" in skill_names, "plugin skill not found"
        assert "project-skill" in skill_names, "project skill not found"

    def test_project_skill_overrides_plugin_skill(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """Project skill with same name overrides plugin skill."""
        import brynhild.plugins.loader as loader
        import brynhild.skills as skills

        # Load the test-complete plugin
        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(TEST_COMPLETE_PLUGIN)

        # Create a project skill with SAME NAME as plugin skill
        project_skills = tmp_path / ".brynhild" / "skills" / "debugging"
        project_skills.mkdir(parents=True)
        (project_skills / "SKILL.md").write_text("""---
name: debugging
description: PROJECT OVERRIDE debugging skill
---

[PROJECT-OVERRIDE-BODY]
""")

        # Create registry with plugin AND project root
        registry = skills.SkillRegistry(
            project_root=tmp_path,
            plugins=[plugin],
        )

        # Get debugging skill
        debugging_skill = registry.get_skill("debugging")
        assert debugging_skill is not None

        # Project skill should override plugin skill (higher priority)
        assert debugging_skill.source == "project"
        assert "PROJECT OVERRIDE" in debugging_skill.description

        # Trigger and verify body is from project
        triggered = registry.trigger_skill("debugging")
        assert triggered is not None
        assert "[PROJECT-OVERRIDE-BODY]" in triggered
        # Plugin body marker should NOT be present
        assert "[TEST-PLUGIN-SKILL: debugging]" not in triggered


class TestPluginSkillDiscoveryPaths:
    """Tests for plugin skill path discovery."""

    def test_get_plugin_skill_paths(self) -> None:
        """get_plugin_skill_paths returns correct paths."""
        import brynhild.plugins.loader as loader
        import brynhild.skills.discovery as discovery

        # Load the test-complete plugin
        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(TEST_COMPLETE_PLUGIN)

        paths = discovery.get_plugin_skill_paths([plugin])

        # Should have one entry for test-complete
        assert len(paths) == 1
        path, name = paths[0]
        assert name == "test-complete"
        assert path == TEST_COMPLETE_PLUGIN / "skills"

    def test_get_plugin_skill_paths_skips_disabled(self) -> None:
        """get_plugin_skill_paths skips disabled plugins."""
        import brynhild.plugins.loader as loader
        import brynhild.skills.discovery as discovery

        # Load the test-complete plugin and disable it
        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(TEST_COMPLETE_PLUGIN)
        plugin.enabled = False

        paths = discovery.get_plugin_skill_paths([plugin])

        # Should be empty since plugin is disabled
        assert paths == []

    def test_get_plugin_skill_paths_skips_no_skills(self) -> None:
        """get_plugin_skill_paths skips plugins without skills."""
        import brynhild.plugins.loader as loader
        import brynhild.skills.discovery as discovery

        # Load test-ollama plugin (has providers but no skills)
        test_ollama = PLUGINS_DIR / "test-ollama"
        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(test_ollama)

        paths = discovery.get_plugin_skill_paths([plugin])

        # Should be empty since plugin has no skills
        assert paths == []


class TestPluginSkillSearchPaths:
    """Tests for skill search paths with plugins."""

    def test_get_skill_search_paths_includes_plugins(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """get_skill_search_paths includes plugin paths when provided."""
        import brynhild.plugins.loader as loader
        import brynhild.skills.discovery as discovery

        # Load the test-complete plugin
        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(TEST_COMPLETE_PLUGIN)

        paths = discovery.get_skill_search_paths(
            project_root=tmp_path,
            plugins=[plugin],
        )

        # Plugin skills path should be in the list
        plugin_skills_path = TEST_COMPLETE_PLUGIN / "skills"
        assert plugin_skills_path in paths

    def test_plugin_skills_after_global_before_project(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """Plugin skill paths come after global but before project."""
        import brynhild.plugins.loader as loader
        import brynhild.skills.discovery as discovery

        # Load the test-complete plugin
        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(TEST_COMPLETE_PLUGIN)

        paths = discovery.get_skill_search_paths(
            project_root=tmp_path,
            plugins=[plugin],
        )

        # Find indices
        plugin_skills_path = TEST_COMPLETE_PLUGIN / "skills"
        global_path = discovery.get_global_skills_path()
        project_path = discovery.get_project_skills_path(tmp_path)

        plugin_idx = paths.index(plugin_skills_path)
        global_idx = paths.index(global_path)
        project_idx = paths.index(project_path)

        # Order: ... global ... plugin ... project
        assert global_idx < plugin_idx < project_idx


class TestSkillDiscoveryWithPlugins:
    """Tests for SkillDiscovery class with plugins."""

    def test_discovery_with_plugins(self) -> None:
        """SkillDiscovery finds skills from plugins."""
        import brynhild.plugins.loader as loader
        import brynhild.skills.discovery as discovery

        # Load the test-complete plugin
        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(TEST_COMPLETE_PLUGIN)

        # Create discovery with plugins
        disc = discovery.SkillDiscovery(
            project_root=FIXTURES_DIR,
            plugins=[plugin],
        )

        skills = disc.discover()

        assert "debugging" in skills
        assert "testing" in skills

    def test_discovery_source_for_plugin_path(self) -> None:
        """SkillDiscovery._get_source_for_path returns plugin source."""
        import brynhild.plugins.loader as loader
        import brynhild.skills.discovery as discovery

        # Load the test-complete plugin
        plugin_loader = loader.PluginLoader()
        plugin = plugin_loader.load(TEST_COMPLETE_PLUGIN)

        # Create discovery with plugins
        disc = discovery.SkillDiscovery(
            project_root=FIXTURES_DIR,
            plugins=[plugin],
        )

        plugin_skills_path = TEST_COMPLETE_PLUGIN / "skills"
        source = disc._get_source_for_path(plugin_skills_path)

        assert source == "plugin:test-complete"

