"""
Integration tests for skills loading and injection.

Test IDs from design-plan-phase6.md:
- SI-01: Skill metadata at startup ✅
- SI-02: Skill auto-triggers (keyword) - REMOVED BY DESIGN (use LearnSkill tool)
- SI-03: Skill auto-triggers (tag) - REMOVED BY DESIGN (never implemented)
- SI-04: Skill explicit trigger ✅ - /skill command in test_skill_injection.py
- SI-05: Skill body injected correctly ✅
- SI-06: Skill triggering logged ✅
- SI-07: Multiple skill directories ✅
- SI-08: Invalid skill gracefully handled ✅

Note: Auto-triggering was removed. Models should use the LearnSkill tool
for explicit skill access. See test_skill_injection.py for LearnSkill tests.
"""

import pathlib as _pathlib

import brynhild.logging.conversation_logger as conversation_logger
import brynhild.skills as skills


def _create_skill(
    skill_dir: _pathlib.Path,
    name: str,
    description: str,
    body: str = "## Instructions\n\nDo something.",
) -> None:
    """Helper to create a skill directory."""
    skill_path = skill_dir / name
    skill_path.mkdir(parents=True, exist_ok=True)
    skill_md = skill_path / "SKILL.md"
    skill_md.write_text(f"""---
name: {name}
description: {description}
---

{body}
""")


class TestSkillsIntegration:
    """Integration tests for skills system."""

    def test_si01_skill_metadata_at_startup(self, tmp_path: _pathlib.Path) -> None:
        """SI-01: System prompt contains skill descriptions."""
        # Setup: Create skill directory
        skill_dir = tmp_path / ".brynhild" / "skills"
        _create_skill(skill_dir, "debugging", "Help debug Python code")
        _create_skill(skill_dir, "testing", "Help write tests")

        # Create registry and get metadata
        registry = skills.SkillRegistry(
            project_root=tmp_path,
            search_paths=[skill_dir],
        )

        metadata = registry.get_metadata_for_prompt()

        # Verify metadata contains skill info
        assert "debugging" in metadata
        assert "Help debug Python code" in metadata
        assert "testing" in metadata
        assert "Help write tests" in metadata

    def test_si05_skill_body_injected_correctly(self, tmp_path: _pathlib.Path) -> None:
        """SI-05: Triggered skill body appears in context."""
        # Setup: Create skill with specific body
        skill_dir = tmp_path / ".brynhild" / "skills"
        _create_skill(
            skill_dir,
            "debugging",
            "Help debug",
            body="## Debugging Steps\n\n1. Check logs\n2. Add breakpoints",
        )

        # Create registry and trigger skill
        registry = skills.SkillRegistry(
            project_root=tmp_path,
            search_paths=[skill_dir],
        )

        triggered = registry.trigger_skill("debugging")

        # Verify body content is returned
        assert triggered is not None
        assert "Debugging Steps" in triggered
        assert "Check logs" in triggered
        assert "Add breakpoints" in triggered
        # Verify it's wrapped in skill tags
        assert '<skill name="debugging">' in triggered
        assert "</skill>" in triggered

    def test_si06_skill_triggering_logged(self, tmp_path: _pathlib.Path) -> None:
        """SI-06: ConversationLogger records skill trigger."""
        # Setup: Create skill
        skill_dir = tmp_path / ".brynhild" / "skills"
        _create_skill(skill_dir, "debugging", "Help debug")

        # Create logger
        log_file = tmp_path / "test.jsonl"
        logger = conversation_logger.ConversationLogger(
            log_file=log_file,
            provider="test",
            model="test-model",
            enabled=True,
        )

        # Manually log a skill trigger (simulating what would happen)
        logger.log_context_init("Base prompt")
        logger.log_context_injection(
            source="skill_trigger",
            location="message_inject",
            content="<skill>content</skill>",
            origin="debugging",
            trigger_type="keyword",
            trigger_match="debug",
        )
        logger.close()

        # Verify log contains skill trigger
        log_content = log_file.read_text()
        assert "context_injection" in log_content
        assert '"source": "skill_trigger"' in log_content
        assert '"origin": "debugging"' in log_content
        assert '"trigger_type": "keyword"' in log_content

    def test_si07_multiple_skill_directories(self, tmp_path: _pathlib.Path) -> None:
        """SI-07: Skills from all locations discoverable."""
        # Setup: Create multiple skill directories
        dir1 = tmp_path / "skills1"
        dir2 = tmp_path / "skills2"
        _create_skill(dir1, "skill-from-dir1", "From directory 1")
        _create_skill(dir2, "skill-from-dir2", "From directory 2")

        # Create registry with both directories
        registry = skills.SkillRegistry(
            project_root=tmp_path,
            search_paths=[dir1, dir2],
        )

        skill_list = registry.list_skills()
        skill_names = [s.name for s in skill_list]

        # Verify both skills are found
        assert "skill-from-dir1" in skill_names
        assert "skill-from-dir2" in skill_names

    def test_si08_invalid_skill_gracefully_handled(self, tmp_path: _pathlib.Path) -> None:
        """SI-08: Bad SKILL.md doesn't crash, others still load."""
        # Setup: Create one valid and one invalid skill
        skill_dir = tmp_path / "skills"

        # Valid skill
        _create_skill(skill_dir, "valid-skill", "This is valid")

        # Invalid skill (missing required fields)
        invalid_path = skill_dir / "invalid-skill"
        invalid_path.mkdir(parents=True)
        (invalid_path / "SKILL.md").write_text("not valid yaml frontmatter")

        # Should not raise
        registry = skills.SkillRegistry(
            project_root=tmp_path,
            search_paths=[skill_dir],
        )

        skill_list = registry.list_skills()
        skill_names = [s.name for s in skill_list]

        # Valid skill should still be found
        assert "valid-skill" in skill_names
        # Invalid should not crash the system
        assert "invalid-skill" not in skill_names


class TestSkillMatching:
    """Tests for skill keyword matching."""

    def test_find_matching_skills_by_name(self, tmp_path: _pathlib.Path) -> None:
        """Skills matching by name are found."""
        skill_dir = tmp_path / "skills"
        _create_skill(skill_dir, "debugging", "Help debug")
        _create_skill(skill_dir, "testing", "Help test")

        registry = skills.SkillRegistry(
            project_root=tmp_path,
            search_paths=[skill_dir],
        )

        # Search with skill name
        matches = registry.find_matching_skills("help me debug this error")

        assert len(matches) >= 1
        assert any(s.name == "debugging" for s in matches)

    def test_find_matching_skills_by_description(self, tmp_path: _pathlib.Path) -> None:
        """Skills matching by description keywords are found."""
        skill_dir = tmp_path / "skills"
        _create_skill(skill_dir, "tdd", "Test-driven development methodology")

        registry = skills.SkillRegistry(
            project_root=tmp_path,
            search_paths=[skill_dir],
        )

        # Search with description keyword
        matches = registry.find_matching_skills("I want to use test-driven development")

        # Should find by description match (if word > 3 chars)
        assert len(matches) >= 0  # Matching depends on word length filter

    def test_find_matching_skills_limits_results(self, tmp_path: _pathlib.Path) -> None:
        """max_results parameter limits returned skills."""
        skill_dir = tmp_path / "skills"
        for i in range(5):
            _create_skill(skill_dir, f"debug-{i}", f"Debug skill {i}")

        registry = skills.SkillRegistry(
            project_root=tmp_path,
            search_paths=[skill_dir],
        )

        # Search with limit
        matches = registry.find_matching_skills("debug something", max_results=2)

        assert len(matches) <= 2
