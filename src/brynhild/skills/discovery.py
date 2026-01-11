"""
Skill discovery from standard locations and entry points.

Skills are discovered from (in priority order, lowest to highest):
1. Builtin skills (shipped with brynhild package)
2. ~/.config/brynhild/skills/ - User skills (global)
3. $BRYNHILD_SKILL_PATH - Custom paths (colon-separated)
4. Plugin-bundled skills - Skills from directory-based plugins
5. Entry point skills - Skills from packaged plugins (brynhild.skills)
6. Project .brynhild/skills/ - Project-local skills

Later sources have higher priority (project overrides plugin overrides global overrides builtin).

Entry point plugins can register skills via:
    [project.entry-points."brynhild.skills"]
    my-skill = "my_package.skills:get_skill"

The function should return either:
    - A Skill instance
    - A dict with 'name', 'description', and 'body' keys
"""

from __future__ import annotations

import importlib.metadata as _meta
import logging as _logging
import os as _os
import pathlib as _pathlib
import typing as _typing

import brynhild.builtin_skills as builtin_skills
import brynhild.skills.skill as skill_module

if _typing.TYPE_CHECKING:
    import brynhild.plugins.manifest as _manifest

_logger = _logging.getLogger(__name__)


def get_builtin_skills_path() -> _pathlib.Path:
    """Get the path to builtin skills directory (shipped with package)."""
    return builtin_skills.get_builtin_skills_path()


def get_global_skills_path() -> _pathlib.Path:
    """Get the path to global skills directory."""
    return _pathlib.Path.home() / ".config" / "brynhild" / "skills"


def get_project_skills_path(project_root: _pathlib.Path) -> _pathlib.Path:
    """Get the path to project-local skills directory."""
    return project_root / ".brynhild" / "skills"


def get_plugin_skill_paths(
    plugins: list[_manifest.Plugin] | None = None,
) -> list[tuple[_pathlib.Path, str]]:
    """
    Get skill paths from directory-based plugins.

    Note: Entry-point plugins should use 'brynhild.skills' entry points instead.

    Args:
        plugins: List of enabled plugins.

    Returns:
        List of (skill_path, plugin_name) tuples.
    """
    if not plugins:
        return []

    paths: list[tuple[_pathlib.Path, str]] = []
    for plugin in plugins:
        # Skip entry-point plugins (they don't have filesystem paths)
        if plugin.is_packaged:
            continue
        if plugin.enabled and plugin.has_skills():
            skills_dir = plugin.skills_path
            if skills_dir.is_dir():
                paths.append((skills_dir, plugin.name))

    return paths


def _entry_points_disabled() -> bool:
    """Check if entry point plugin discovery is disabled."""
    import os as _os
    return _os.environ.get("BRYNHILD_DISABLE_ENTRY_POINT_PLUGINS", "").lower() in (
        "1", "true", "yes"
    )


def discover_skills_from_entry_points() -> dict[str, skill_module.Skill]:
    """
    Discover skills registered via the 'brynhild.skills' entry point group.

    Entry point format in pyproject.toml:
        [project.entry-points."brynhild.skills"]
        my-skill = "my_package.skills:get_skill"

    The function should return:
        - A Skill instance, OR
        - A dict with 'name', 'description', and 'body' keys

    Can be disabled by setting BRYNHILD_DISABLE_ENTRY_POINT_PLUGINS=1.

    Returns:
        Dict mapping skill name to Skill instance.
    """
    if _entry_points_disabled():
        _logger.debug("Entry point skills discovery disabled by environment variable")
        return {}

    skills: dict[str, skill_module.Skill] = {}

    eps = _meta.entry_points(group="brynhild.skills")

    for ep in eps:
        try:
            skill_provider = ep.load()

            # Call if callable, otherwise use as-is
            result = skill_provider() if callable(skill_provider) else skill_provider

            if isinstance(result, skill_module.Skill):
                skill = result
            elif isinstance(result, dict):
                # Build Skill from dict
                # Require at minimum: name, description, body
                if "name" not in result or "description" not in result:
                    _logger.warning(
                        "Entry point '%s' dict missing required 'name' or 'description'",
                        ep.name,
                    )
                    continue

                # Build frontmatter dict for validation
                # Support both 'allowed_tools' and 'allowed-tools' keys
                fm_data = {
                    "name": result["name"],
                    "description": result["description"],
                }
                if "license" in result:
                    fm_data["license"] = result["license"]
                if "allowed_tools" in result:
                    fm_data["allowed-tools"] = result["allowed_tools"]
                elif "allowed-tools" in result:
                    fm_data["allowed-tools"] = result["allowed-tools"]
                if "metadata" in result:
                    fm_data["metadata"] = result["metadata"]

                frontmatter = skill_module.SkillFrontmatter.model_validate(fm_data)
                skill = skill_module.Skill(
                    frontmatter=frontmatter,
                    body=result.get("body", ""),
                    path=_pathlib.Path("<entry-point>"),
                    source=f"entry_point:{ep.name}",
                )
            else:
                _logger.warning(
                    "Entry point '%s' returned unexpected type: %s "
                    "(expected Skill or dict)",
                    ep.name,
                    type(result).__name__,
                )
                continue

            skills[skill.name] = skill

            _logger.debug(
                "Discovered skill '%s' from entry point '%s' (package: %s)",
                skill.name,
                ep.name,
                getattr(ep.dist, "name", "unknown") if ep.dist else "unknown",
            )
        except Exception as e:
            _logger.warning(
                "Failed to load skill from entry point '%s': %s",
                ep.name,
                e,
            )

    return skills


def get_skill_search_paths(
    project_root: _pathlib.Path | None = None,
    *,
    include_builtin: bool = True,
    plugins: list[_manifest.Plugin] | None = None,
) -> list[_pathlib.Path]:
    """
    Get all skill search paths in priority order.

    Args:
        project_root: Project root directory. If None, only global,
                      builtin, and env paths are included.
        include_builtin: Whether to include builtin skills (default True).
        plugins: List of enabled plugins to include skills from.

    Returns:
        List of paths to search (lowest to highest priority).
    """
    paths: list[_pathlib.Path] = []

    # 1. Builtin skills (lowest priority)
    if include_builtin:
        paths.append(get_builtin_skills_path())

    # 2. Global skills
    paths.append(get_global_skills_path())

    # 3. Environment variable paths
    env_path = _os.environ.get("BRYNHILD_SKILL_PATH", "")
    if env_path:
        for p in env_path.split(":"):
            p = p.strip()
            if p:
                paths.append(_pathlib.Path(p).expanduser().resolve())

    # 4. Plugin-bundled skills
    for plugin_path, _plugin_name in get_plugin_skill_paths(plugins):
        paths.append(plugin_path)

    # 5. Project-local skills (highest priority)
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
        plugins: list[_manifest.Plugin] | None = None,
    ) -> None:
        """
        Initialize skill discovery.

        Args:
            project_root: Project root for local skill discovery.
            search_paths: Custom search paths (overrides default locations).
            plugins: List of enabled plugins to include skills from.
        """
        self._project_root = project_root
        self._search_paths = search_paths
        self._plugins = plugins or []
        # Build mapping of plugin skill paths for source identification
        self._plugin_paths: dict[_pathlib.Path, str] = {}
        for path, name in get_plugin_skill_paths(self._plugins):
            self._plugin_paths[path] = name

    def get_search_paths(self) -> list[_pathlib.Path]:
        """Get the search paths in use."""
        if self._search_paths is not None:
            return self._search_paths
        return get_skill_search_paths(self._project_root, plugins=self._plugins)

    def _get_source_for_path(self, search_path: _pathlib.Path) -> str:
        """Determine the source type for a search path."""
        builtin_path = get_builtin_skills_path()
        global_path = get_global_skills_path()
        if search_path == builtin_path:
            return "builtin"
        if search_path == global_path:
            return "global"
        if search_path in self._plugin_paths:
            return f"plugin:{self._plugin_paths[search_path]}"
        if self._project_root and search_path == get_project_skills_path(
            self._project_root
        ):
            return "project"
        return "custom"

    def discover(self) -> dict[str, skill_module.Skill]:
        """
        Discover all skills from search paths and entry points.

        Sources in order (later overrides earlier):
        1. Directory-based sources (builtin, global, env, plugins, project)
        2. Entry point skills (brynhild.skills)

        Later sources override earlier sources (by skill name).

        Returns:
            Dict mapping skill name to Skill instance.
        """
        skills: dict[str, skill_module.Skill] = {}

        # 1. Directory-based skills
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

        # 2. Entry point skills (highest priority among non-project sources)
        # Note: Project skills still have highest priority as they come last
        # in get_search_paths(), but entry point skills override other plugins
        entry_point_skills = discover_skills_from_entry_points()
        for name, skill in entry_point_skills.items():
            # Only override if not a project skill
            if name not in skills or not skills[name].source.startswith("project"):
                skills[name] = skill

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

