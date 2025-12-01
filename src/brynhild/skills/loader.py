"""
Skill loader with progressive disclosure.

Implements the three-level loading strategy:
1. Metadata only (at startup) - ~100 tokens per skill
2. Full body (when triggered) - < 5k tokens
3. Reference files (as needed) - loaded on demand
"""

from __future__ import annotations

import pathlib as _pathlib
import typing as _typing

import brynhild.skills.skill as skill_module


class SkillLoader:
    """
    Loader for progressive skill content disclosure.

    Skills are loaded in stages:
    - Level 1: Metadata only (name + description) at startup
    - Level 2: Full SKILL.md body when skill is triggered
    - Level 3: Reference files loaded as needed
    """

    def __init__(self, skills: dict[str, skill_module.Skill] | None = None) -> None:
        """
        Initialize the skill loader.

        Args:
            skills: Pre-loaded skills dict (name -> Skill).
        """
        self._skills = skills or {}
        self._loaded_refs: dict[str, dict[str, str]] = {}  # skill -> file -> content

    def set_skills(self, skills: dict[str, skill_module.Skill]) -> None:
        """Set the available skills."""
        self._skills = skills
        self._loaded_refs = {}

    def get_skill(self, name: str) -> skill_module.Skill | None:
        """Get a skill by name."""
        return self._skills.get(name)

    def list_skills(self) -> list[skill_module.Skill]:
        """List all available skills."""
        return list(self._skills.values())

    # Level 1: Metadata for system prompt
    def get_all_metadata(self) -> str:
        """
        Get metadata for all skills (Level 1).

        Returns a compact string with name and description for each
        skill, suitable for inclusion in the system prompt.

        Returns:
            Formatted skill metadata.
        """
        if not self._skills:
            return ""

        lines = ["## Available Skills", ""]
        for skill in sorted(self._skills.values(), key=lambda s: s.name):
            lines.append(skill.get_metadata_for_prompt())
        lines.append("")
        lines.append(
            "To use a skill, either let it activate automatically based on your "
            "task, or explicitly request it with /skill <name>."
        )

        return "\n".join(lines)

    def get_skill_metadata(self, name: str) -> str | None:
        """
        Get metadata for a specific skill (Level 1).

        Args:
            name: Skill name.

        Returns:
            Skill metadata string, or None if not found.
        """
        skill = self._skills.get(name)
        if skill is None:
            return None
        return skill.get_metadata_for_prompt()

    # Level 2: Full body when triggered
    def get_skill_body(self, name: str) -> str | None:
        """
        Get the full skill body (Level 2).

        Args:
            name: Skill name.

        Returns:
            Full SKILL.md body, or None if not found.
        """
        skill = self._skills.get(name)
        if skill is None:
            return None
        return skill.get_full_content()

    def trigger_skill(self, name: str) -> str | None:
        """
        Trigger a skill and get its content for injection.

        This is the main method called when a skill is triggered
        (either automatically or explicitly). Returns the skill
        body wrapped in appropriate markers.

        Args:
            name: Skill name.

        Returns:
            Skill content ready for injection, or None if not found.
        """
        skill = self._skills.get(name)
        if skill is None:
            return None

        body = skill.get_full_content()
        return f"""<skill name="{name}">
{body}
</skill>"""

    # Level 3: Reference files on demand
    def get_reference_file(self, skill_name: str, filename: str) -> str | None:
        """
        Get a reference file from a skill (Level 3).

        Reference files are additional .md files in the skill directory
        that can be loaded on demand.

        Args:
            skill_name: Skill name.
            filename: Reference file name (e.g., "examples.md").

        Returns:
            File content, or None if not found.
        """
        skill = self._skills.get(skill_name)
        if skill is None:
            return None

        # Check cache first
        if skill_name in self._loaded_refs and filename in self._loaded_refs[skill_name]:
            return self._loaded_refs[skill_name][filename]

        # Load from disk
        ref_path = skill.path / filename
        if not ref_path.is_file():
            return None

        try:
            content = ref_path.read_text(encoding="utf-8")
            # Cache it
            if skill_name not in self._loaded_refs:
                self._loaded_refs[skill_name] = {}
            self._loaded_refs[skill_name][filename] = content
            return content
        except OSError:
            return None

    def list_reference_files(self, skill_name: str) -> list[str]:
        """
        List available reference files for a skill.

        Args:
            skill_name: Skill name.

        Returns:
            List of reference file names.
        """
        skill = self._skills.get(skill_name)
        if skill is None:
            return []
        return [f.name for f in skill.list_reference_files()]

    def list_scripts(self, skill_name: str) -> list[str]:
        """
        List available scripts for a skill.

        Args:
            skill_name: Skill name.

        Returns:
            List of script file names.
        """
        skill = self._skills.get(skill_name)
        if skill is None:
            return []
        return [s.name for s in skill.list_scripts()]

    def get_script_path(self, skill_name: str, script_name: str) -> _pathlib.Path | None:
        """
        Get the path to a script in a skill.

        Args:
            skill_name: Skill name.
            script_name: Script file name.

        Returns:
            Path to script, or None if not found.
        """
        skill = self._skills.get(skill_name)
        if skill is None:
            return None

        script_path = skill.path / "scripts" / script_name
        if script_path.is_file():
            return script_path
        return None

    def to_dict(self) -> dict[str, _typing.Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "skill_count": len(self._skills),
            "skills": [s.to_dict() for s in self._skills.values()],
            "cached_refs": {
                name: list(files.keys())
                for name, files in self._loaded_refs.items()
            },
        }

