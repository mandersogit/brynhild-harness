"""
LearnSkill tool for LLM access to skills.

This tool gives models explicit control over skill loading,
replacing the opaque auto-trigger system with a standard tool interface.

Supports progressive skill loading:
- Level 1: List all skills (metadata)
- Level 2: Load full skill body
- Level 3: Access reference files and scripts
"""

from __future__ import annotations

import typing as _typing

import brynhild.tools.base as base

if _typing.TYPE_CHECKING:
    import brynhild.skills as skills


class LearnSkillTool(base.Tool):
    """
    Load skills to get specialized guidance for tasks.

    Supports progressive loading:
    - LearnSkill() → List all available skills
    - LearnSkill(skill="name") → Load full skill guidance
    - LearnSkill(skill="name", info=True) → Show metadata + available resources
    - LearnSkill(skill="name", reference="file.md") → Get reference file content
    - LearnSkill(skill="name", script="helper.py") → Get script path
    """

    @property
    def name(self) -> str:
        return "LearnSkill"

    @property
    def description(self) -> str:
        return (
            "Load skills to get specialized guidance for tasks. "
            "Call with no arguments to list skills. "
            "Call with skill name to load full guidance. "
            "Use info=true to see available references and scripts. "
            "Use reference or script parameter to access specific resources."
        )

    @property
    def requires_permission(self) -> bool:
        return False  # Read-only

    def __init__(
        self,
        skill_registry: skills.SkillRegistry,
    ) -> None:
        """
        Initialize the LearnSkill tool.

        Args:
            skill_registry: Registry of available skills.
        """
        self._registry = skill_registry

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def categories(self) -> list[str]:
        return ["skills", "learning"]

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {
            "type": "object",
            "properties": {
                "skill": {
                    "type": "string",
                    "description": (
                        "Skill name. Omit to list all available skills."
                    ),
                },
                "info": {
                    "type": "boolean",
                    "description": (
                        "If true, show skill metadata and available resources "
                        "instead of loading the full body."
                    ),
                },
                "reference": {
                    "type": "string",
                    "description": (
                        "Name of reference file to retrieve (e.g., 'patterns.md'). "
                        "Requires skill parameter."
                    ),
                },
                "script": {
                    "type": "string",
                    "description": (
                        "Name of script to get path for (e.g., 'helper.py'). "
                        "Requires skill parameter."
                    ),
                },
            },
            "required": [],
        }

    async def execute(
        self,
        input: dict[str, _typing.Any],
    ) -> base.ToolResult:
        """
        Execute the LearnSkill tool.

        Args:
            input: Tool input with optional parameters.

        Returns:
            ToolResult with skill content or resource.
        """
        skill_name = input.get("skill", "").strip().lower()
        info_only = input.get("info", False)
        reference_name = input.get("reference", "").strip()
        script_name = input.get("script", "").strip()

        # No skill → list all skills
        if not skill_name:
            return self._list_skills()

        # Validate skill exists before any operation
        skill = self._registry.get_skill(skill_name)
        if skill is None:
            available = [s.name for s in self._registry.list_skills()]
            return base.ToolResult(
                success=False,
                output="",
                error=(
                    f"Skill '{skill_name}' not found.\n\n"
                    f"Available skills: {', '.join(sorted(available))}"
                ),
            )

        # Get reference file
        if reference_name:
            return self._get_reference(skill_name, reference_name)

        # Get script path
        if script_name:
            return self._get_script_path(skill_name, script_name)

        # Info mode - metadata + resources list
        if info_only:
            return self._get_skill_info(skill)

        # Default - load full skill body
        return self._load_skill(skill_name)

    def _list_skills(self) -> base.ToolResult:
        """List all available skills."""
        skill_list = self._registry.list_skills()

        if not skill_list:
            return base.ToolResult(
                success=True,
                output="No skills available.",
            )

        lines = ["Available skills:", ""]
        for skill in sorted(skill_list, key=lambda s: s.name):
            lines.append(f"- **{skill.name}**: {skill.description}")
        lines.append("")
        lines.append('Use LearnSkill(skill="name") to load a skill\'s full guidance.')
        lines.append('Use LearnSkill(skill="name", info=true) to see available resources.')

        return base.ToolResult(
            success=True,
            output="\n".join(lines),
        )

    def _load_skill(self, skill_name: str) -> base.ToolResult:
        """Load a skill's full body."""
        content = self._registry.trigger_skill(skill_name)

        if content is None:
            # This shouldn't happen since we validated above
            return base.ToolResult(
                success=False,
                output="",
                error=f"Failed to load skill '{skill_name}'.",
            )

        return base.ToolResult(
            success=True,
            output=content,
        )

    def _get_skill_info(self, skill: _typing.Any) -> base.ToolResult:
        """Get skill metadata and available resources."""
        lines = [
            f"# Skill: {skill.name}",
            "",
            f"**Description**: {skill.description}",
            "",
        ]

        # List reference files
        ref_files = skill.list_reference_files()
        if ref_files:
            lines.append("**Reference files**:")
            for ref in ref_files:
                lines.append(f"  - {ref.name}")
            lines.append("")
        else:
            lines.append("**Reference files**: None")
            lines.append("")

        # List scripts
        scripts = skill.list_scripts()
        if scripts:
            lines.append("**Scripts**:")
            for script in scripts:
                lines.append(f"  - {script.name}")
            lines.append("")
        else:
            lines.append("**Scripts**: None")
            lines.append("")

        lines.append("---")
        lines.append(f'Use LearnSkill(skill="{skill.name}") to load full guidance.')
        if ref_files:
            lines.append(
                f'Use LearnSkill(skill="{skill.name}", reference="filename.md") '
                "to get a reference file."
            )
        if scripts:
            lines.append(
                f'Use LearnSkill(skill="{skill.name}", script="scriptname") '
                "to get a script path."
            )

        return base.ToolResult(
            success=True,
            output="\n".join(lines),
        )

    def _get_reference(self, skill_name: str, reference_name: str) -> base.ToolResult:
        """Get a reference file from a skill."""
        content = self._registry.get_reference_file(skill_name, reference_name)

        if content is None:
            # List available reference files
            skill = self._registry.get_skill(skill_name)
            if skill:
                refs = skill.list_reference_files()
                available = [r.name for r in refs]
                if available:
                    return base.ToolResult(
                        success=False,
                        output="",
                        error=(
                            f"Reference '{reference_name}' not found in skill '{skill_name}'.\n\n"
                            f"Available references: {', '.join(sorted(available))}"
                        ),
                    )
            return base.ToolResult(
                success=False,
                output="",
                error=f"Reference '{reference_name}' not found in skill '{skill_name}'.",
            )

        return base.ToolResult(
            success=True,
            output=content,
        )

    def _get_script_path(self, skill_name: str, script_name: str) -> base.ToolResult:
        """Get the path to a script in a skill."""
        # Access the loader through the registry
        skill = self._registry.get_skill(skill_name)
        if skill is None:
            return base.ToolResult(
                success=False,
                output="",
                error=f"Skill '{skill_name}' not found.",
            )

        # Look for the script
        script_path = skill.path / "scripts" / script_name
        if not script_path.is_file():
            # List available scripts
            scripts = skill.list_scripts()
            available = [s.name for s in scripts]
            if available:
                return base.ToolResult(
                    success=False,
                    output="",
                    error=(
                        f"Script '{script_name}' not found in skill '{skill_name}'.\n\n"
                        f"Available scripts: {', '.join(sorted(available))}"
                    ),
                )
            return base.ToolResult(
                success=False,
                output="",
                error=f"Script '{script_name}' not found in skill '{skill_name}'.",
            )

        return base.ToolResult(
            success=True,
            output=str(script_path.resolve()),
        )
