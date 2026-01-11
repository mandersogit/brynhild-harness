"""
Test skills for entry point discovery integration tests.

Demonstrates skills registration via 'brynhild.skills' entry point.
"""

from __future__ import annotations

import pathlib as _pathlib


def get_skill():
    """
    Get the skill for this plugin.

    Called automatically when Brynhild discovers skills via the
    'brynhild.skills' entry point.

    Returns:
        A Skill instance, or a dict with 'name', 'description', and 'body' keys.
    """
    # Import here to avoid circular imports during discovery
    import brynhild.skills.skill as skill_module

    return skill_module.Skill(
        frontmatter=skill_module.SkillFrontmatter(
            name="test-skill",
            description="A test skill from an entry point plugin for testing skill discovery",
        ),
        body="""
# Test Skill from Entry Point Plugin

This skill was loaded via the `brynhild.skills` entry point.

## Instructions

When this skill is active, the LLM should:

1. Acknowledge that the test skill is loaded
2. Demonstrate that entry point skill discovery works
3. Follow any additional instructions provided

## Example Usage

User: What skills are available?
Assistant: I have the test-skill loaded from an entry point plugin.
""".strip(),
        path=_pathlib.Path("<entry-point>"),
        source="entry_point",
    )


def get_skill_as_dict():
    """
    Alternative: Get skill as a raw dict.

    This demonstrates that skills can also be provided as dicts
    with the required keys.
    """
    return {
        "name": "test-skill-dict",
        "description": "A test skill provided as a dict",
        "body": "This skill was loaded from a dict return value.",
    }

