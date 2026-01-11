"""
Example rules for the plugin template.

Rules are registered in pyproject.toml:

    [project.entry-points."brynhild.rules"]
    my-rules = "brynhild_my_plugin.rules:get_rules"

The entry point can return:
- A string (single rule)
- A list of strings (multiple rules)
- A callable that returns either

Rules are project-specific instructions that get injected into the
system prompt. They're similar to .cursor/rules/ files but distributed
via plugins.
"""


def get_rules() -> str:
    """
    Return project rules.

    Rules provide context-specific instructions to the LLM.
    They're useful for enforcing coding standards, project conventions,
    or domain-specific requirements.

    Returns:
        String containing the rules content.
    """
    return """
# Plugin Template Rules

## Code Style
- Use descriptive variable names
- Add docstrings to all public functions
- Follow PEP 8 conventions

## Plugin Development
- Always test plugins before distribution
- Document all entry points clearly
- Include example usage in README

## Safety
- Never execute untrusted code
- Validate all user inputs
- Handle errors gracefully
"""


# Alternative: Return a list of rules (each becomes a separate rule entry)
#
# def get_rules():
#     return [
#         "Rule 1: Always validate inputs",
#         "Rule 2: Handle errors gracefully",
#         "Rule 3: Document your code",
#     ]


# Alternative: Return the rules string directly
#
# get_rules = """
# # My Rules
# - Rule 1
# - Rule 2
# """

