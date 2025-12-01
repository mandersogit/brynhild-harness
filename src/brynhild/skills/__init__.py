"""
Agent Skills system for Brynhild.

Skills are modular capabilities that extend Brynhild with domain-specific
expertise. They provide:
- Instructions that activate automatically when relevant
- Progressive disclosure (only load what's needed)
- Optional scripts and reference materials

Skill discovery locations (in priority order):
1. ~/.config/brynhild/skills/ - User skills
2. $BRYNHILD_SKILL_PATH - Custom paths (colon-separated)
3. Project .brynhild/skills/ - Project-local skills
4. Plugin-bundled skills - Skills bundled in plugins

Based on Anthropic's Agent Skills Spec and obra/superpowers.
"""

from brynhild.skills.discovery import (
    SkillDiscovery,
    get_global_skills_path,
    get_project_skills_path,
    get_skill_search_paths,
)
from brynhild.skills.loader import SkillLoader
from brynhild.skills.registry import SkillRegistry
from brynhild.skills.skill import (
    SKILL_BODY_SOFT_LIMIT,
    Skill,
    SkillFrontmatter,
    load_skill,
    parse_skill_markdown,
)

__all__ = [
    # Core
    "Skill",
    "SkillFrontmatter",
    "SKILL_BODY_SOFT_LIMIT",
    # Parsing
    "load_skill",
    "parse_skill_markdown",
    # Discovery
    "SkillDiscovery",
    "get_global_skills_path",
    "get_project_skills_path",
    "get_skill_search_paths",
    # Loader and Registry
    "SkillLoader",
    "SkillRegistry",
]

