"""
Example skill for the plugin template.

Skills are registered in pyproject.toml:

    [project.entry-points."brynhild.skills"]
    my-skill = "brynhild_my_plugin.skills:get_skill"

The entry point can return:
- A Skill instance
- A dict with name, description, body fields
- A callable that returns either

Skills provide behavioral guidance to the LLM, like specialized knowledge
or instructions for handling specific domains.
"""

import brynhild.skills.skill as skill


def get_skill() -> skill.Skill:
    """
    Return the skill definition.

    Skills are injected into the system prompt to guide LLM behavior.

    Returns:
        Skill instance with metadata and content.
    """
    return skill.Skill(
        # Skill identifier - lowercase with hyphens
        name="my-skill",
        # Short description for listings
        description="Example skill demonstrating plugin skills",
        # The actual skill content (appears in system prompt)
        body="""
# My Custom Skill

This skill provides specialized guidance for the LLM.

## Guidelines

1. Always be helpful and informative
2. Use the greeter tool when users want to say hello
3. Use the counter tool for counting operations

## Best Practices

- Provide clear explanations
- Ask for clarification if requests are ambiguous
- Suggest related operations the user might find useful
""",
        # Optional: restrict which tools this skill can use
        allowed_tools=["greeter", "counter"],
        # Optional: source path (for directory-based skills)
        source=None,
        # Optional: whether skill is triggered by globs/files
        globs=None,
    )


# Alternative: Return a dict instead of Skill
#
# def get_skill():
#     return {
#         "name": "my-skill",
#         "description": "Example skill",
#         "body": "Skill content here...",
#         "allowed_tools": ["greeter"],
#     }


# Alternative: Return a Skill directly (for simpler cases)
#
# get_skill = skill.Skill(
#     name="my-skill",
#     description="Example skill",
#     body="Skill content...",
# )

