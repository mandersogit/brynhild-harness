"""
Skill discovery from standard locations.

Skills are discovered from (in priority order):
1. ~/.config/brynhild/skills/ - User skills (global)
2. $BRYNHILD_SKILL_PATH - Custom paths (colon-separated)
3. Project .brynhild/skills/ - Project-local skills

Later sources have higher priority (project overrides global).
"""

from __future__ import annotations

import os as _os
import pathlib as _pathlib
import typing as _typing

import brynhild.skills.skill as skill_module


def get_global_skills_path() -> _pathlib.Path:
    """Get the path to global skills directory."""
    return _pathlib.Path.home() / ".config" / "brynhild" / "skills"


def get_project_skills_path(project_root: _pathlib.Path) -> _pathlib.Path:
    """Get the path to project-local skills directory."""
    return project_root / ".brynhild" / "skills"


def get_skill_search_paths(
    project_root: _pathlib.Path | None = None,
) -> list[_pathlib.Path]:
    """
    Get all skill search paths in priority order.

    Args:
        project_root: Project root directory. If None, only global
                      and env paths are included.

    Returns:
        List of paths to search (lowest to highest priority).
    """
    paths: list[_pathlib.Path] = []

    # 1. Global skills (lowest priority)
    paths.append(get_global_skills_path())

    # 2. Environment variable paths
    env_path = _os.environ.get("BRYNHILD_SKILL_PATH", "")
    if env_path:
        for p in env_path.split(":"):
            p = p.strip()
            if p:
                paths.append(_pathlib.Path(p).expanduser().resolve())

    # 3. Project-local skills (highest priority)
    if project_root is not None:
        paths.append(get_project_skills_path(project_root))

    return paths


class SkillDiscovery:
    """
    Discovers skills from standard locations.

    Scans skill directories and returns discovered Skill instances.
    Later sources (project-local) have higher priority than earlier
    sources (global) - skills with the same name from later sources
    replace earlier ones.
    """

    def __init__(
        self,
        project_root: _pathlib.Path | None = None,
        search_paths: list[_pathlib.Path] | None = None,
    ) -> None:
        """
        Initialize skill discovery.

        Args:
            project_root: Project root for local skill discovery.
            search_paths: Custom search paths (overrides default locations).
        """
        self._project_root = project_root
        self._search_paths = search_paths

    def get_search_paths(self) -> list[_pathlib.Path]:
        """Get the search paths in use."""
        if self._search_paths is not None:
            return self._search_paths
        return get_skill_search_paths(self._project_root)

    def _get_source_for_path(self, search_path: _pathlib.Path) -> str:
        """Determine the source type for a search path."""
        global_path = get_global_skills_path()
        if search_path == global_path:
            return "global"
        if self._project_root and search_path == get_project_skills_path(
            self._project_root
        ):
            return "project"
        return "custom"

    def discover(self) -> dict[str, skill_module.Skill]:
        """
        Discover all skills from search paths.

        Later sources override earlier sources (by skill name).

        Returns:
            Dict mapping skill name to Skill instance.
        """
        skills: dict[str, skill_module.Skill] = {}

        for search_path in self.get_search_paths():
            if not search_path.is_dir():
                continue

            source = self._get_source_for_path(search_path)

            for skill_dir in sorted(search_path.iterdir()):
                if not skill_dir.is_dir():
                    continue

                skill_file = skill_dir / "SKILL.md"
                if not skill_file.exists():
                    continue

                try:
                    skill = skill_module.load_skill(skill_dir, source=source)
                    # Later sources override earlier (by name)
                    skills[skill.name] = skill
                except (FileNotFoundError, ValueError):
                    # Skip invalid skills
                    continue

        return skills

    def discover_all(
        self,
        *,
        include_errors: bool = False,
    ) -> _typing.Iterator[
        skill_module.Skill | tuple[_pathlib.Path, Exception]
    ]:
        """
        Discover all skills, optionally including errors.

        This is an iterator that yields skills as they're discovered,
        and optionally yields (path, exception) tuples for invalid skills.

        Args:
            include_errors: If True, yield (path, exception) for failures.

        Yields:
            Skill instances, or (path, exception) tuples if include_errors.
        """
        for search_path in self.get_search_paths():
            if not search_path.is_dir():
                continue

            source = self._get_source_for_path(search_path)

            for skill_dir in sorted(search_path.iterdir()):
                if not skill_dir.is_dir():
                    continue

                skill_file = skill_dir / "SKILL.md"
                if not skill_file.exists():
                    continue

                try:
                    skill = skill_module.load_skill(skill_dir, source=source)
                    yield skill
                except (FileNotFoundError, ValueError) as e:
                    if include_errors:
                        yield (skill_dir, e)

