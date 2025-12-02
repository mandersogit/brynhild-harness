"""
Skill definition and SKILL.md parsing.

Skills are defined by a SKILL.md file with YAML frontmatter.
The frontmatter contains metadata; the body contains instructions.
"""

from __future__ import annotations

import dataclasses as _dataclasses
import logging as _logging
import pathlib as _pathlib
import re as _re
import typing as _typing

import pydantic as _pydantic
import yaml as _yaml

_logger = _logging.getLogger(__name__)

# Soft limit for SKILL.md body (lines) - matches Anthropic guidance
SKILL_BODY_SOFT_LIMIT = 500

# Regex to extract YAML frontmatter from markdown
_FRONTMATTER_RE = _re.compile(
    r"^---\s*\n(.*?)\n---\s*\n?(.*)$",
    _re.DOTALL,
)


class SkillFrontmatter(_pydantic.BaseModel):
    """
    Frontmatter parsed from a SKILL.md file.

    Required fields:
    - name: Skill identifier (must match directory name)
    - description: What the skill does AND when to use it

    Optional fields provide additional metadata.
    """

    model_config = _pydantic.ConfigDict(extra="allow")

    # Required fields
    name: str = _pydantic.Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$",
        description="Skill name (lowercase, hyphens allowed)",
    )

    description: str = _pydantic.Field(
        ...,
        min_length=1,
        max_length=1024,
        description="What the skill does and when to use it",
    )

    # Optional fields
    license: str | None = _pydantic.Field(
        default=None,
        description="License for the skill",
    )

    allowed_tools: list[str] = _pydantic.Field(
        default_factory=list,
        alias="allowed-tools",
        description="Tools pre-approved for use with this skill",
    )

    metadata: dict[str, _typing.Any] = _pydantic.Field(
        default_factory=dict,
        description="Custom metadata for client-specific data",
    )


@_dataclasses.dataclass
class Skill:
    """
    A parsed skill ready for use.

    The skill body contains instructions that are loaded when
    the skill is triggered. Additional files in the skill
    directory can be loaded progressively as needed.
    """

    frontmatter: SkillFrontmatter
    """Parsed frontmatter metadata."""

    body: str
    """Skill instructions (markdown body after frontmatter)."""

    path: _pathlib.Path
    """Path to skill directory."""

    source: str = "project"
    """Where the skill was discovered from (global, project, plugin)."""

    @property
    def name(self) -> str:
        """Skill name from frontmatter."""
        return self.frontmatter.name

    @property
    def description(self) -> str:
        """Skill description from frontmatter."""
        return self.frontmatter.description

    @property
    def license(self) -> str | None:
        """Skill license from frontmatter."""
        return self.frontmatter.license

    @property
    def allowed_tools(self) -> list[str]:
        """Pre-approved tools from frontmatter."""
        return self.frontmatter.allowed_tools

    @property
    def skill_file(self) -> _pathlib.Path:
        """Path to the SKILL.md file."""
        return self.path / "SKILL.md"

    @property
    def body_line_count(self) -> int:
        """Number of lines in the skill body."""
        return len(self.body.splitlines())

    @property
    def exceeds_soft_limit(self) -> bool:
        """Whether body exceeds the soft limit."""
        return self.body_line_count > SKILL_BODY_SOFT_LIMIT

    def list_reference_files(self) -> list[_pathlib.Path]:
        """
        List reference files in the skill's references/ directory.

        Returns all files in references/ (typically .md files).
        Also includes any top-level .md files except SKILL.md for backwards compat.
        """
        refs: list[_pathlib.Path] = []

        # Check references/ directory (preferred location per Anthropic spec)
        refs_dir = self.path / "references"
        if refs_dir.is_dir():
            for ref_file in refs_dir.iterdir():
                if ref_file.is_file() and not ref_file.name.startswith("."):
                    refs.append(ref_file)

        # Also check top-level .md files (backwards compatibility)
        if self.path.is_dir():
            for md_file in self.path.glob("*.md"):
                if md_file.name != "SKILL.md":
                    refs.append(md_file)

        return refs

    def list_scripts(self) -> list[_pathlib.Path]:
        """
        List scripts in the skill's scripts/ directory.

        Returns all executable files (.sh, .py, etc.)
        """
        scripts: list[_pathlib.Path] = []
        scripts_dir = self.path / "scripts"
        if scripts_dir.is_dir():
            for script in scripts_dir.iterdir():
                if script.is_file() and not script.name.startswith("."):
                    scripts.append(script)
        return scripts

    def get_metadata_for_prompt(self) -> str:
        """
        Get minimal metadata for system prompt (Level 1).

        Returns name and description only (~100 tokens).
        """
        return f"**{self.name}**: {self.description}"

    def get_full_content(self) -> str:
        """
        Get full skill content for context (Level 2).

        Returns the complete SKILL.md body.
        """
        return self.body

    def to_dict(self) -> dict[str, _typing.Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "path": str(self.path),
            "source": self.source,
            "license": self.license,
            "allowed_tools": self.allowed_tools,
            "body_lines": self.body_line_count,
            "exceeds_limit": self.exceeds_soft_limit,
            "reference_files": [str(f) for f in self.list_reference_files()],
            "scripts": [str(s) for s in self.list_scripts()],
        }


def parse_skill_markdown(content: str) -> tuple[SkillFrontmatter, str]:
    """
    Parse a SKILL.md file into frontmatter and body.

    Args:
        content: Raw markdown content.

    Returns:
        Tuple of (frontmatter, body).

    Raises:
        ValueError: If frontmatter is missing or invalid.
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        raise ValueError("SKILL.md must have YAML frontmatter (---)")

    frontmatter_yaml = match.group(1)
    body = match.group(2).strip()

    try:
        data = _yaml.safe_load(frontmatter_yaml) or {}
        frontmatter = SkillFrontmatter.model_validate(data)
    except _yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in frontmatter: {e}") from e
    except _pydantic.ValidationError as e:
        raise ValueError(f"Invalid skill frontmatter: {e}") from e

    return frontmatter, body


def load_skill(
    skill_dir: _pathlib.Path,
    source: str = "project",
) -> Skill:
    """
    Load a skill from a directory.

    Args:
        skill_dir: Path to skill directory (must contain SKILL.md).
        source: Where the skill was discovered from.

    Returns:
        Parsed Skill instance.

    Raises:
        FileNotFoundError: If SKILL.md doesn't exist.
        ValueError: If SKILL.md is invalid.
    """
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        raise FileNotFoundError(f"SKILL.md not found: {skill_file}")

    content = skill_file.read_text(encoding="utf-8")
    frontmatter, body = parse_skill_markdown(content)

    # Warn if body exceeds soft limit
    line_count = len(body.splitlines())
    if line_count > SKILL_BODY_SOFT_LIMIT:
        _logger.warning(
            "Skill %s exceeds recommended body limit (%d lines > %d)",
            frontmatter.name,
            line_count,
            SKILL_BODY_SOFT_LIMIT,
        )

    return Skill(
        frontmatter=frontmatter,
        body=body,
        path=skill_dir.resolve(),
        source=source,
    )

