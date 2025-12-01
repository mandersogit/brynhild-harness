"""
Context builder for constructing conversation context with injections.

This module centralizes the logic for building the system prompt with:
- Rules (AGENTS.md, .cursorrules, etc.)
- Skill metadata
- Profile customizations

All injections are logged for debugging and replay.
"""

import dataclasses as _dataclasses
import pathlib as _pathlib

import brynhild.logging as brynhild_logging
import brynhild.plugins.rules as rules
import brynhild.profiles.manager as profiles_manager
import brynhild.profiles.types as profiles_types
import brynhild.skills as skills


@_dataclasses.dataclass
class ContextInjection:
    """Record of a context injection."""

    source: str
    """Injection source type (rules, skill_metadata, profile, etc.)."""

    location: str
    """Where injected (system_prompt_prepend, system_prompt_append, etc.)."""

    content: str
    """The actual content injected."""

    origin: str | None = None
    """Source identifier (file path, skill name, etc.)."""


@_dataclasses.dataclass
class ConversationContext:
    """Complete context for a conversation."""

    system_prompt: str
    """The final system prompt with all injections applied."""

    base_prompt: str
    """The original base system prompt before injections."""

    injections: list[ContextInjection]
    """List of all injections applied."""

    profile: profiles_types.ModelProfile | None = None
    """The profile used (if any)."""


class ContextBuilder:
    """
    Builder for conversation context.

    Handles loading rules, skills, and profiles, and constructs
    the final system prompt with all injections logged.
    """

    def __init__(
        self,
        *,
        project_root: _pathlib.Path | None = None,
        logger: brynhild_logging.ConversationLogger | None = None,
        include_rules: bool = True,
        include_skills: bool = True,
        profile_name: str | None = None,
        model: str | None = None,
        provider: str | None = None,
    ) -> None:
        """
        Initialize the context builder.

        Args:
            project_root: Project root for discovery.
            logger: Logger for recording injections.
            include_rules: Whether to load and inject rules.
            include_skills: Whether to load and inject skill metadata.
            profile_name: Explicit profile name to use.
            model: Model name for profile resolution.
            provider: Provider name for profile resolution.
        """
        self._project_root = project_root or _pathlib.Path.cwd()
        self._logger = logger
        self._include_rules = include_rules
        self._include_skills = include_skills
        self._profile_name = profile_name
        self._model = model
        self._provider = provider

        # Lazy-loaded components
        self._rules_manager: rules.RulesManager | None = None
        self._skill_registry: skills.SkillRegistry | None = None
        self._profile_manager: profiles_manager.ProfileManager | None = None

    def _get_rules_manager(self) -> rules.RulesManager:
        """Get or create the rules manager."""
        if self._rules_manager is None:
            self._rules_manager = rules.RulesManager(
                project_root=self._project_root,
            )
        return self._rules_manager

    def _get_skill_registry(self) -> skills.SkillRegistry:
        """Get or create the skill registry."""
        if self._skill_registry is None:
            self._skill_registry = skills.SkillRegistry(
                project_root=self._project_root,
            )
        return self._skill_registry

    def _get_profile_manager(self) -> profiles_manager.ProfileManager:
        """Get or create the profile manager."""
        if self._profile_manager is None:
            self._profile_manager = profiles_manager.ProfileManager()
        return self._profile_manager

    def _resolve_profile(self) -> profiles_types.ModelProfile | None:
        """Resolve the profile to use."""
        manager = self._get_profile_manager()

        # Explicit profile name takes precedence
        if self._profile_name:
            profile = manager.get_profile(self._profile_name)
            if profile:
                return profile

        # Otherwise resolve from model
        if self._model:
            return manager.resolve(self._model, self._provider)

        return None

    def build(self, base_system_prompt: str) -> ConversationContext:
        """
        Build the complete conversation context.

        Args:
            base_system_prompt: The base system prompt to enhance.

        Returns:
            ConversationContext with the final system prompt and metadata.
        """
        injections: list[ContextInjection] = []
        prepend_parts: list[str] = []
        append_parts: list[str] = []

        # Log context initialization
        if self._logger:
            self._logger.log_context_init(base_system_prompt)

        # 1. Load and inject rules (prepended)
        if self._include_rules:
            rules_content = self._get_rules_manager().get_rules_for_prompt()
            if rules_content:
                prepend_parts.append(rules_content)
                injection = ContextInjection(
                    source="rules",
                    location="system_prompt_prepend",
                    content=rules_content,
                    origin=str(self._project_root),
                )
                injections.append(injection)

                # Log each rule file separately for better tracking
                for rule_file in self._get_rules_manager().list_rule_files():
                    if self._logger:
                        self._logger.log_context_injection(
                            source="rules",
                            location="system_prompt_prepend",
                            content=rules_content,  # Log combined content
                            origin=rule_file["path"],
                            trigger_type="startup",
                        )
                    break  # Only log once (combined content)

        # 2. Resolve and apply profile
        profile = self._resolve_profile()
        working_prompt = base_system_prompt

        if profile:
            # Apply profile prefix/suffix/patterns
            working_prompt = profile.build_system_prompt(base_system_prompt)

            # Log profile injections
            if profile.system_prompt_prefix:
                injection = ContextInjection(
                    source="profile",
                    location="system_prompt_prepend",
                    content=profile.system_prompt_prefix,
                    origin=profile.name,
                )
                injections.append(injection)

                if self._logger:
                    self._logger.log_context_injection(
                        source="profile",
                        location="system_prompt_prepend",
                        content=profile.system_prompt_prefix,
                        origin=profile.name,
                        trigger_type="startup",
                        metadata={"profile_field": "system_prompt_prefix"},
                    )

            if profile.system_prompt_suffix:
                injection = ContextInjection(
                    source="profile",
                    location="system_prompt_append",
                    content=profile.system_prompt_suffix,
                    origin=profile.name,
                )
                injections.append(injection)

                if self._logger:
                    self._logger.log_context_injection(
                        source="profile",
                        location="system_prompt_append",
                        content=profile.system_prompt_suffix,
                        origin=profile.name,
                        trigger_type="startup",
                        metadata={"profile_field": "system_prompt_suffix"},
                    )

            patterns_text = profile.get_enabled_patterns_text()
            if patterns_text:
                injection = ContextInjection(
                    source="profile",
                    location="system_prompt_prepend",
                    content=patterns_text,
                    origin=profile.name,
                )
                injections.append(injection)

                if self._logger:
                    self._logger.log_context_injection(
                        source="profile",
                        location="system_prompt_prepend",
                        content=patterns_text,
                        origin=profile.name,
                        trigger_type="startup",
                        metadata={
                            "profile_field": "prompt_patterns",
                            "enabled_patterns": profile.enabled_patterns,
                        },
                    )

        # 3. Load and inject skill metadata (appended)
        if self._include_skills:
            skill_metadata = self._get_skill_registry().get_metadata_for_prompt()
            if skill_metadata:
                append_parts.append(skill_metadata)
                injection = ContextInjection(
                    source="skill_metadata",
                    location="system_prompt_append",
                    content=skill_metadata,
                    origin="all_skills",
                )
                injections.append(injection)

                if self._logger:
                    self._logger.log_context_injection(
                        source="skill_metadata",
                        location="system_prompt_append",
                        content=skill_metadata,
                        origin="all_skills",
                        trigger_type="startup",
                        metadata={
                            "skill_count": len(self._get_skill_registry().list_skills()),
                        },
                    )

        # Build final system prompt
        final_parts: list[str] = []

        # Prepend parts (rules)
        if prepend_parts:
            final_parts.extend(prepend_parts)

        # The working prompt (base + profile prefix/suffix/patterns)
        final_parts.append(working_prompt)

        # Append parts (skills)
        if append_parts:
            final_parts.extend(append_parts)

        final_prompt = "\n\n".join(final_parts)

        # Log context ready
        if self._logger:
            import hashlib as _hashlib

            prompt_hash = _hashlib.sha256(final_prompt.encode()).hexdigest()[:16]
            self._logger.log_context_ready(prompt_hash)

        return ConversationContext(
            system_prompt=final_prompt,
            base_prompt=base_system_prompt,
            injections=injections,
            profile=profile,
        )

    def get_skill_registry(self) -> skills.SkillRegistry:
        """Get the skill registry for runtime skill triggering."""
        return self._get_skill_registry()


def build_context(
    base_system_prompt: str,
    *,
    project_root: _pathlib.Path | None = None,
    logger: brynhild_logging.ConversationLogger | None = None,
    include_rules: bool = True,
    include_skills: bool = True,
    profile_name: str | None = None,
    model: str | None = None,
    provider: str | None = None,
) -> ConversationContext:
    """
    Convenience function to build conversation context.

    Args:
        base_system_prompt: The base system prompt to enhance.
        project_root: Project root for discovery.
        logger: Logger for recording injections.
        include_rules: Whether to load and inject rules.
        include_skills: Whether to load and inject skill metadata.
        profile_name: Explicit profile name to use.
        model: Model name for profile resolution.
        provider: Provider name for profile resolution.

    Returns:
        ConversationContext with the final system prompt and metadata.
    """
    builder = ContextBuilder(
        project_root=project_root,
        logger=logger,
        include_rules=include_rules,
        include_skills=include_skills,
        profile_name=profile_name,
        model=model,
        provider=provider,
    )
    return builder.build(base_system_prompt)

