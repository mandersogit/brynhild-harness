"""
Agent Skills system for Brynhild.

Skills are modular capabilities that extend Brynhild with domain-specific
expertise. They provide:
- Instructions that activate automatically when relevant
- Progressive disclosure (only load what's needed)
- Optional scripts and reference materials

Skill discovery locations (in priority order, lowest to highest):
1. Builtin skills (shipped with brynhild package)
2. ~/.config/brynhild/skills/ - User skills (global)
3. $BRYNHILD_SKILL_PATH - Custom paths (colon-separated)
4. Plugin-bundled skills - Skills from directory-based plugins
5. Entry point skills - Skills from packaged plugins (brynhild.skills)
6. Project .brynhild/skills/ - Project-local skills

Based on Anthropic's Agent Skills Spec and obra/superpowers.
"""

from brynhild.skills.discovery import (
    SkillDiscovery,
    discover_skills_from_entry_points,
    get_global_skills_path,
    get_plugin_skill_paths,
    get_project_skills_path,
    get_skill_search_paths,
)
from brynhild.skills.loader import SkillLoader
from brynhild.skills.preprocessor import (
    SkillPreprocessResult,
    format_skill_injection_message,
    preprocess_for_skills,
)
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
    "discover_skills_from_entry_points",
    "get_global_skills_path",
    "get_plugin_skill_paths",
    "get_project_skills_path",
    "get_skill_search_paths",
    # Loader and Registry
    "SkillLoader",
    "SkillRegistry",
    # Preprocessing
    "SkillPreprocessResult",
    "preprocess_for_skills",
    "format_skill_injection_message",
]

