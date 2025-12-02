"""
Skill registry for managing available skills.

The registry coordinates skill discovery, loading, and provides
the interface for skill triggering.
"""

from __future__ import annotations

import pathlib as _pathlib
import typing as _typing

import brynhild.skills.discovery as discovery
import brynhild.skills.loader as loader
import brynhild.skills.skill as skill_module

if _typing.TYPE_CHECKING:
    import brynhild.plugins.manifest as _manifest


class SkillRegistry:
    """
    Registry for managing skills.

    Handles:
    - Skill discovery from standard locations
    - Progressive skill loading
    - Skill triggering (automatic and explicit)
    """

    def __init__(
        self,
        project_root: _pathlib.Path | None = None,
        search_paths: list[_pathlib.Path] | None = None,
        plugins: list[_manifest.Plugin] | None = None,
    ) -> None:
        """
        Initialize the skill registry.

        Args:
            project_root: Project root for skill discovery.
            search_paths: Custom search paths (overrides defaults).
            plugins: List of enabled plugins to include skills from.
        """
        self._project_root = project_root
        self._plugins = plugins
        self._discovery = discovery.SkillDiscovery(
            project_root, search_paths, plugins=plugins
        )
        self._loader = loader.SkillLoader()
        self._skills: dict[str, skill_module.Skill] | None = None

    def _ensure_discovered(self) -> None:
        """Ensure skills have been discovered."""
        if self._skills is None:
            self._skills = self._discovery.discover()
            self._loader.set_skills(self._skills)

    def discover(self) -> None:
        """Force re-discovery of skills."""
        self._skills = None
        self._ensure_discovered()

    # Skill listing
    def list_skills(self) -> list[skill_module.Skill]:
        """
        List all discovered skills.

        Returns:
            List of Skill instances.
        """
        self._ensure_discovered()
        return self._loader.list_skills()

    def get_skill(self, name: str) -> skill_module.Skill | None:
        """
        Get a skill by name.

        Args:
            name: Skill name.

        Returns:
            Skill instance or None if not found.
        """
        self._ensure_discovered()
        return self._loader.get_skill(name)

    def has_skill(self, name: str) -> bool:
        """
        Check if a skill exists.

        Args:
            name: Skill name.

        Returns:
            True if skill exists.
        """
        return self.get_skill(name) is not None

    # Progressive loading interface
    def get_metadata_for_prompt(self) -> str:
        """
        Get all skill metadata for system prompt (Level 1).

        Returns:
            Formatted skill metadata string.
        """
        self._ensure_discovered()
        return self._loader.get_all_metadata()

    def trigger_skill(self, name: str) -> str | None:
        """
        Trigger a skill and get its content (Level 2).

        Args:
            name: Skill name.

        Returns:
            Skill content for injection, or None if not found.
        """
        self._ensure_discovered()
        return self._loader.trigger_skill(name)

    def get_reference_file(self, skill_name: str, filename: str) -> str | None:
        """
        Get a reference file from a skill (Level 3).

        Args:
            skill_name: Skill name.
            filename: Reference file name.

        Returns:
            File content, or None if not found.
        """
        self._ensure_discovered()
        return self._loader.get_reference_file(skill_name, filename)

    # Skill matching
    def find_matching_skills(
        self,
        user_input: str,
        *,
        max_results: int = 3,
    ) -> list[skill_module.Skill]:
        """
        Find skills that might match user input.

        This is a simple keyword matching implementation.
        More sophisticated matching (embeddings, etc.) can be
        added later.

        Args:
            user_input: User's message or request.
            max_results: Maximum number of skills to return.

        Returns:
            List of potentially matching skills.
        """
        self._ensure_discovered()
        assert self._skills is not None

        user_lower = user_input.lower()
        matches: list[tuple[skill_module.Skill, int]] = []

        for skill in self._skills.values():
            score = 0

            # Check if skill name appears in input
            if skill.name in user_lower or skill.name.replace("-", " ") in user_lower:
                score += 10

            # Check description keywords
            desc_words = skill.description.lower().split()
            for word in desc_words:
                if len(word) > 3 and word in user_lower:
                    score += 1

            if score > 0:
                matches.append((skill, score))

        # Sort by score and return top results
        matches.sort(key=lambda x: x[1], reverse=True)
        return [skill for skill, _ in matches[:max_results]]

    # Serialization
    def to_dict(self) -> dict[str, _typing.Any]:
        """Convert to dictionary for JSON serialization."""
        self._ensure_discovered()
        return {
            "project_root": str(self._project_root) if self._project_root else None,
            "skill_count": len(self._skills) if self._skills else 0,
            "skills": [s.to_dict() for s in self.list_skills()],
        }

