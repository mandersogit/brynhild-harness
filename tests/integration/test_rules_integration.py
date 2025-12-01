"""
Integration tests for rules loading and injection.

Test IDs from design-plan-phase6.md:
- RI-01: Rules loaded at session start
- RI-02: AGENTS.md discovered
- RI-03: .cursorrules discovered
- RI-04: Multiple rule files concatenate
- RI-05: Missing rule files handled
- RI-06: Rules logged
"""

import pathlib as _pathlib

import brynhild.core.context as context
import brynhild.logging.conversation_logger as conversation_logger
import brynhild.plugins.rules as rules


class TestRulesIntegration:
    """Integration tests for rules system."""

    def test_ri01_rules_loaded_at_session_start(self, tmp_path: _pathlib.Path) -> None:
        """RI-01: System prompt contains rules content when rules exist."""
        # Setup: Create AGENTS.md
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("# Project Rules\n\nAlways use Python 3.11+")

        # Build context
        ctx = context.build_context(
            "Base prompt",
            project_root=tmp_path,
            include_rules=True,
            include_skills=False,
        )

        # Verify rules are in system prompt
        assert "Project Rules" in ctx.system_prompt
        assert "Always use Python 3.11+" in ctx.system_prompt

    def test_ri02_agents_md_discovered(self, tmp_path: _pathlib.Path) -> None:
        """RI-02: RulesManager finds and loads AGENTS.md in project."""
        # Setup: Create AGENTS.md
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("# AGENTS.md Content\n\nSpecific instructions here.")

        # Use RulesManager directly
        manager = rules.RulesManager(project_root=tmp_path, include_global=False)
        loaded_rules = manager.load_rules()

        # Verify AGENTS.md content is loaded
        assert "AGENTS.md Content" in loaded_rules
        assert "Specific instructions" in loaded_rules

        # Verify it's in the discovered files list
        files = manager.list_rule_files()
        assert any("AGENTS.md" in f["path"] for f in files)

    def test_ri03_cursorrules_discovered(self, tmp_path: _pathlib.Path) -> None:
        """RI-03: RulesManager finds and loads .cursorrules."""
        # Setup: Create .cursorrules
        cursorrules = tmp_path / ".cursorrules"
        cursorrules.write_text("# Cursor Rules\n\nUse type hints everywhere.")

        # Use RulesManager directly
        manager = rules.RulesManager(project_root=tmp_path, include_global=False)
        loaded_rules = manager.load_rules()

        # Verify .cursorrules content is loaded
        assert "Cursor Rules" in loaded_rules
        assert "type hints" in loaded_rules

        # Verify it's in the discovered files list
        files = manager.list_rule_files()
        assert any(".cursorrules" in f["path"] for f in files)

    def test_ri04_multiple_rule_files_concatenate(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """RI-04: Rules from multiple sources appear in order."""
        # Setup: Create multiple rule files
        (tmp_path / "AGENTS.md").write_text("# From AGENTS.md")
        (tmp_path / ".cursorrules").write_text("# From cursorrules")
        (tmp_path / "rules.md").write_text("# From rules.md")

        # Use RulesManager
        manager = rules.RulesManager(project_root=tmp_path, include_global=False)
        loaded_rules = manager.load_rules()

        # Verify all files are included
        assert "From AGENTS.md" in loaded_rules
        assert "From cursorrules" in loaded_rules
        assert "From rules.md" in loaded_rules

        # Verify separator is used
        assert "---" in loaded_rules

    def test_ri05_missing_rule_files_handled(self, tmp_path: _pathlib.Path) -> None:
        """RI-05: No error when optional rule files don't exist."""
        # Setup: Empty directory (no rule files)

        # Should not raise
        manager = rules.RulesManager(project_root=tmp_path, include_global=False)
        loaded_rules = manager.load_rules()

        # Should return empty string, not raise
        assert loaded_rules == ""

        # Context building should also work
        ctx = context.build_context(
            "Base prompt",
            project_root=tmp_path,
            include_rules=True,
            include_skills=False,
        )

        # Base prompt should be unchanged
        assert ctx.system_prompt == "Base prompt"

    def test_ri06_rules_logged(self, tmp_path: _pathlib.Path) -> None:
        """RI-06: ConversationLogger records rules injection."""
        # Setup: Create AGENTS.md
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("# Logged Rules Content")

        # Create logger
        log_file = tmp_path / "test.jsonl"
        logger = conversation_logger.ConversationLogger(
            log_file=log_file,
            provider="test",
            model="test-model",
            enabled=True,
        )

        # Build context with logging
        context.build_context(
            "Base prompt",
            project_root=tmp_path,
            logger=logger,
            include_rules=True,
            include_skills=False,
        )
        logger.close()

        # Verify log contains rules injection
        log_content = log_file.read_text()
        assert "context_injection" in log_content
        assert '"source": "rules"' in log_content
        assert "Logged Rules Content" in log_content


class TestRulesWalkToRoot:
    """Test rules discovery walking up directory tree."""

    def test_discovers_rules_in_parent_directories(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """Rules in parent directories are discovered."""
        # Setup: Create nested structure
        parent = tmp_path / "parent"
        child = parent / "child"
        child.mkdir(parents=True)

        (parent / "AGENTS.md").write_text("# Parent rules")
        (child / "AGENTS.md").write_text("# Child rules")

        # Discover from child
        found = rules.discover_rule_files(child)

        # Should find both (parent first, then child)
        paths_str = [str(p) for p in found]
        assert any("parent/AGENTS.md" in p for p in paths_str)
        assert any("child/AGENTS.md" in p for p in paths_str)

    def test_stop_at_limits_walk(self, tmp_path: _pathlib.Path) -> None:
        """stop_at parameter limits directory walking."""
        # Setup: Create nested structure
        grandparent = tmp_path / "gp"
        parent = grandparent / "parent"
        child = parent / "child"
        child.mkdir(parents=True)

        (grandparent / "AGENTS.md").write_text("# Grandparent")
        (parent / "AGENTS.md").write_text("# Parent")
        (child / "AGENTS.md").write_text("# Child")

        # Discover from child, stop at parent
        found = rules.discover_rule_files(child, stop_at=parent)

        paths_str = [str(p) for p in found]
        # Should NOT find grandparent
        assert not any("gp/AGENTS.md" in p and "parent" not in p for p in paths_str)
        # Should find parent and child
        assert any("parent/AGENTS.md" in p for p in paths_str)
        assert any("child/AGENTS.md" in p for p in paths_str)

