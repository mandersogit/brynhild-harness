"""
Skill preprocessing for user messages.

Handles explicit `/skill <name>` commands from users.

When a skill is triggered via command, this module returns the skill body
for injection into the conversation as a system message.

Note: Auto-triggering based on keywords was removed by design.
Models should use the LearnSkill tool for explicit skill access.
"""

from __future__ import annotations

import dataclasses as _dataclasses
import logging as _logging
import re as _re
import typing as _typing

import brynhild.skills.registry as skill_registry

_logger = _logging.getLogger(__name__)

# Regex to match /skill commands
# Matches: /skill name, /skill name rest of message
_SKILL_COMMAND_RE = _re.compile(
    r"^/skill\s+([a-z0-9][a-z0-9-]*[a-z0-9]|[a-z0-9])(?:\s+(.*))?$",
    _re.IGNORECASE | _re.DOTALL,
)


@_dataclasses.dataclass
class SkillPreprocessResult:
    """Result of preprocessing a user message for skills."""

    user_message: str
    """The user message (possibly modified if /skill command was stripped)."""

    skill_injection: str | None
    """Skill content to inject, or None if no skill triggered."""

    skill_name: str | None
    """Name of triggered skill, or None."""

    trigger_type: _typing.Literal["explicit"] | None
    """How the skill was triggered (always 'explicit' if triggered)."""

    error: str | None
    """Error message if skill lookup failed."""


def preprocess_for_skills(
    user_message: str,
    registry: skill_registry.SkillRegistry | None,
) -> SkillPreprocessResult:
    """
    Preprocess a user message for skill triggers.

    Checks for explicit `/skill <name>` command only.
    Auto-triggering has been removed by design - models should
    use the LearnSkill tool for explicit skill access.

    Args:
        user_message: The raw user message.
        registry: SkillRegistry for skill lookup. If None, returns unchanged.

    Returns:
        SkillPreprocessResult with potential skill injection.
    """
    if registry is None:
        return SkillPreprocessResult(
            user_message=user_message,
            skill_injection=None,
            skill_name=None,
            trigger_type=None,
            error=None,
        )

    # Check for explicit /skill command
    match = _SKILL_COMMAND_RE.match(user_message.strip())
    if match:
        skill_name = match.group(1).lower()
        rest_of_message = match.group(2) or ""

        _logger.debug("Explicit skill command: /skill %s", skill_name)

        content = registry.trigger_skill(skill_name)
        if content is None:
            # Skill not found - return error but keep original message
            available = [s.name for s in registry.list_skills()]
            return SkillPreprocessResult(
                user_message=user_message,
                skill_injection=None,
                skill_name=skill_name,
                trigger_type="explicit",
                error=f"Skill '{skill_name}' not found. Available: {', '.join(available)}",
            )

        # Successfully found skill
        # The user message becomes the rest after /skill name, or empty
        final_message = rest_of_message.strip() if rest_of_message else ""

        return SkillPreprocessResult(
            user_message=final_message,
            skill_injection=content,
            skill_name=skill_name,
            trigger_type="explicit",
            error=None,
        )

    # No skill triggered - return unchanged
    return SkillPreprocessResult(
        user_message=user_message,
        skill_injection=None,
        skill_name=None,
        trigger_type=None,
        error=None,
    )


def format_skill_injection_message(content: str, skill_name: str) -> str:
    """
    Format skill content for injection as a system message.

    Args:
        content: The skill body content.
        skill_name: Name of the skill.

    Returns:
        Formatted message for conversation injection.
    """
    return (
        f"[Skill '{skill_name}' activated - follow these instructions:]\n\n"
        f"{content}"
    )
