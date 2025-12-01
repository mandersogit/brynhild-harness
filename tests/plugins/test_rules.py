"""
Tests for rules system.

Tests verify that:
- Rule files are discovered correctly
- Walk-to-root discovery works
- Global and project rules are merged
- Rules are formatted for prompt inclusion
"""

import pathlib as _pathlib
import unittest.mock as _mock

import brynhild.plugins.rules as rules


class TestDiscoverRuleFiles:
    """Tests for discover_rule_files function."""

    def test_finds_agents_md(self, tmp_path: _pathlib.Path) -> None:
        """AGENTS.md is discovered."""
        (tmp_path / "AGENTS.md").write_text("# Rules")

        found = rules.discover_rule_files(tmp_path)

        assert len(found) == 1
        assert found[0].name == "AGENTS.md"

    def test_finds_cursorrules(self, tmp_path: _pathlib.Path) -> None:
        """.cursorrules is discovered."""
        (tmp_path / ".cursorrules").write_text("rules here")

        found = rules.discover_rule_files(tmp_path)

        assert len(found) == 1
        assert found[0].name == ".cursorrules"

    def test_finds_rules_md(self, tmp_path: _pathlib.Path) -> None:
        """rules.md is discovered."""
        (tmp_path / "rules.md").write_text("# Rules")

        found = rules.discover_rule_files(tmp_path)

        assert len(found) == 1
        assert found[0].name == "rules.md"

    def test_finds_brynhild_rules_md(self, tmp_path: _pathlib.Path) -> None:
        """.brynhild/rules.md is discovered."""
        (tmp_path / ".brynhild").mkdir()
        (tmp_path / ".brynhild" / "rules.md").write_text("# Rules")

        found = rules.discover_rule_files(tmp_path)

        assert len(found) == 1
        assert found[0].name == "rules.md"
        assert ".brynhild" in str(found[0])

    def test_finds_multiple_rule_files(self, tmp_path: _pathlib.Path) -> None:
        """Multiple rule files in same directory are all found."""
        (tmp_path / "AGENTS.md").write_text("agents")
        (tmp_path / ".cursorrules").write_text("cursor")
        (tmp_path / "rules.md").write_text("rules")

        found = rules.discover_rule_files(tmp_path)

        assert len(found) == 3
        names = {f.name for f in found}
        assert names == {"AGENTS.md", ".cursorrules", "rules.md"}

    def test_walks_to_root_from_subdir(self, tmp_path: _pathlib.Path) -> None:
        """Rules in parent directories are discovered."""
        # Create directory structure
        subdir = tmp_path / "src" / "module"
        subdir.mkdir(parents=True)
        (tmp_path / "AGENTS.md").write_text("root rules")
        (subdir / "AGENTS.md").write_text("subdir rules")

        # Search from subdir
        found = rules.discover_rule_files(subdir, stop_at=tmp_path)

        # Should find both, root first
        assert len(found) == 2
        # Root rule should be first (lower priority)
        assert found[0] == tmp_path / "AGENTS.md"
        assert found[1] == subdir / "AGENTS.md"

    def test_stop_at_limits_walk(self, tmp_path: _pathlib.Path) -> None:
        """stop_at parameter limits how far up we walk."""
        # Create structure: tmp/parent/project/src
        project = tmp_path / "parent" / "project"
        src = project / "src"
        src.mkdir(parents=True)

        # Rules at different levels
        (tmp_path / "AGENTS.md").write_text("top level")
        (project / "AGENTS.md").write_text("project level")
        (src / "AGENTS.md").write_text("src level")

        # Stop at project - shouldn't find tmp_path rules
        found = rules.discover_rule_files(src, stop_at=project)

        assert len(found) == 2
        paths = [str(f) for f in found]
        assert str(tmp_path / "AGENTS.md") not in paths

    def test_returns_empty_for_no_rules(self, tmp_path: _pathlib.Path) -> None:
        """Returns empty list if no rule files found."""
        found = rules.discover_rule_files(tmp_path, stop_at=tmp_path)
        assert found == []


class TestLoadRuleFile:
    """Tests for load_rule_file function."""

    def test_loads_existing_file(self, tmp_path: _pathlib.Path) -> None:
        """Existing file content is returned."""
        rule_file = tmp_path / "AGENTS.md"
        rule_file.write_text("# My Rules\n\nDo this.")

        content = rules.load_rule_file(rule_file)

        assert content == "# My Rules\n\nDo this."

    def test_returns_none_for_missing_file(self, tmp_path: _pathlib.Path) -> None:
        """Missing file returns None."""
        content = rules.load_rule_file(tmp_path / "nonexistent.md")
        assert content is None


class TestLoadGlobalRules:
    """Tests for load_global_rules function."""

    def test_loads_md_files_from_global_dir(self, tmp_path: _pathlib.Path) -> None:
        """Loads all .md files from global rules directory."""
        global_dir = tmp_path / ".config" / "brynhild" / "rules"
        global_dir.mkdir(parents=True)
        (global_dir / "coding.md").write_text("coding rules")
        (global_dir / "testing.md").write_text("testing rules")

        with _mock.patch.object(rules, "GLOBAL_RULES_DIR", global_dir):
            loaded = rules.load_global_rules()

        assert len(loaded) == 2
        names = {path.name for path, _ in loaded}
        assert names == {"coding.md", "testing.md"}

    def test_returns_empty_if_dir_missing(self) -> None:
        """Returns empty list if global dir doesn't exist."""
        with _mock.patch.object(
            rules, "GLOBAL_RULES_DIR", _pathlib.Path("/nonexistent/path")
        ):
            loaded = rules.load_global_rules()

        assert loaded == []


class TestRulesManager:
    """Tests for RulesManager class."""

    def test_discovers_project_rules(self, tmp_path: _pathlib.Path) -> None:
        """Project rules are discovered."""
        (tmp_path / "AGENTS.md").write_text("# Project Rules")

        manager = rules.RulesManager(
            project_root=tmp_path,
            include_global=False,
        )
        paths = manager.discover_rules()

        assert len(paths) == 1
        assert paths[0].name == "AGENTS.md"

    def test_loads_and_concatenates_rules(self, tmp_path: _pathlib.Path) -> None:
        """Multiple rules are loaded and concatenated."""
        (tmp_path / "AGENTS.md").write_text("Agents rules")
        (tmp_path / ".cursorrules").write_text("Cursor rules")

        manager = rules.RulesManager(
            project_root=tmp_path,
            include_global=False,
        )
        content = manager.load_rules()

        assert "Agents rules" in content
        assert "Cursor rules" in content
        assert "---" in content  # Separator

    def test_caches_loaded_rules(self, tmp_path: _pathlib.Path) -> None:
        """Rules are cached after first load."""
        rule_file = tmp_path / "AGENTS.md"
        rule_file.write_text("Original")

        manager = rules.RulesManager(
            project_root=tmp_path,
            include_global=False,
        )

        first_load = manager.load_rules()
        assert "Original" in first_load

        # Modify file
        rule_file.write_text("Modified")

        # Should return cached version
        cached = manager.load_rules()
        assert "Original" in cached

        # Force reload
        reloaded = manager.load_rules(force_reload=True)
        assert "Modified" in reloaded

    def test_get_rules_for_prompt_wraps_content(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """get_rules_for_prompt wraps rules in XML tags."""
        (tmp_path / "AGENTS.md").write_text("My rules")

        manager = rules.RulesManager(
            project_root=tmp_path,
            include_global=False,
        )
        prompt = manager.get_rules_for_prompt()

        assert "<project_rules>" in prompt
        assert "</project_rules>" in prompt
        assert "My rules" in prompt

    def test_get_rules_for_prompt_empty_returns_empty(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """get_rules_for_prompt returns empty string if no rules."""
        manager = rules.RulesManager(
            project_root=tmp_path,
            include_global=False,
        )
        prompt = manager.get_rules_for_prompt()

        assert prompt == ""

    def test_list_rule_files_includes_metadata(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """list_rule_files returns path, source, and size."""
        (tmp_path / "AGENTS.md").write_text("x" * 100)

        manager = rules.RulesManager(
            project_root=tmp_path,
            include_global=False,
        )
        files = manager.list_rule_files()

        assert len(files) == 1
        assert files[0]["source"] == "project"
        assert files[0]["size"] == 100
        assert "AGENTS.md" in files[0]["path"]

    def test_to_dict_includes_all_info(self, tmp_path: _pathlib.Path) -> None:
        """to_dict includes project_root, files, and total_length."""
        (tmp_path / "AGENTS.md").write_text("rules content")

        manager = rules.RulesManager(
            project_root=tmp_path,
            include_global=False,
        )
        d = manager.to_dict()

        assert d["project_root"] == str(tmp_path)
        assert d["include_global"] is False
        assert len(d["files"]) == 1
        assert d["total_length"] > 0

    def test_global_rules_loaded_first(self, tmp_path: _pathlib.Path) -> None:
        """Global rules are loaded before project rules."""
        # Setup global rules
        global_dir = tmp_path / "global"
        global_dir.mkdir()
        (global_dir / "global.md").write_text("GLOBAL RULES")

        # Setup project rules
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "AGENTS.md").write_text("PROJECT RULES")

        with _mock.patch.object(rules, "GLOBAL_RULES_DIR", global_dir):
            manager = rules.RulesManager(
                project_root=project_dir,
                include_global=True,
            )
            content = manager.load_rules()

        # Global should appear before project
        global_pos = content.find("GLOBAL RULES")
        project_pos = content.find("PROJECT RULES")
        assert global_pos < project_pos


class TestHelperFunctions:
    """Tests for module-level helper functions."""

    def test_rule_files_constant(self) -> None:
        """RULE_FILES contains expected file names."""
        assert "AGENTS.md" in rules.RULE_FILES
        assert ".cursorrules" in rules.RULE_FILES
        assert "rules.md" in rules.RULE_FILES
        assert ".brynhild/rules.md" in rules.RULE_FILES

    def test_get_global_rules_path(self) -> None:
        """get_global_rules_path returns expected path."""
        path = rules.get_global_rules_path()
        assert path.parts[-3:] == (".config", "brynhild", "rules")

