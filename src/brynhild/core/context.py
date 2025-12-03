"""
Context builder for constructing conversation context with injections.

This module centralizes the logic for building the system prompt with:
- Rules (AGENTS.md, .cursorrules, plugin rules, etc.)
- Skill metadata
- Profile customizations
- Hook injections (via CONTEXT_BUILD event)

All injections are logged for debugging and replay.
"""

import dataclasses as _dataclasses
import pathlib as _pathlib
import typing as _typing
import uuid as _uuid

import brynhild.hooks.events as hooks_events
import brynhild.logging as brynhild_logging
import brynhild.plugins.rules as rules
import brynhild.profiles.manager as profiles_manager
import brynhild.profiles.types as profiles_types
import brynhild.skills as skills

if _typing.TYPE_CHECKING:
    import brynhild.hooks.manager as _hooks_manager
    import brynhild.plugins.manifest as _manifest


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

    skill_registry: "skills.SkillRegistry | None" = None
    """The skill registry for runtime skill triggering."""


class ContextBuilder:
    """
    Builder for conversation context.

    Handles loading rules, skills, and profiles, and constructs
    the final system prompt with all injections logged.

    Fires CONTEXT_BUILD hook to allow plugins to inject content.
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
        plugins: "list[_manifest.Plugin] | None" = None,
        hook_manager: "_hooks_manager.HookManager | None" = None,
        session_id: str | None = None,
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
            plugins: List of enabled plugins (for skill and rules discovery).
            hook_manager: Hook manager for firing CONTEXT_BUILD event.
            session_id: Session identifier for hook context.
        """
        self._project_root = project_root or _pathlib.Path.cwd()
        self._logger = logger
        self._include_rules = include_rules
        self._include_skills = include_skills
        self._profile_name = profile_name
        self._model = model
        self._provider = provider
        self._plugins = plugins
        self._hook_manager = hook_manager
        self._session_id = session_id or _uuid.uuid4().hex[:16]

        # Lazy-loaded components
        self._rules_manager: rules.RulesManager | None = None
        self._skill_registry: skills.SkillRegistry | None = None
        self._profile_manager: profiles_manager.ProfileManager | None = None

    def _get_rules_manager(self) -> rules.RulesManager:
        """Get or create the rules manager."""
        if self._rules_manager is None:
            self._rules_manager = rules.RulesManager(
                project_root=self._project_root,
                plugins=self._plugins,
            )
        return self._rules_manager

    def _get_skill_registry(self) -> skills.SkillRegistry:
        """Get or create the skill registry."""
        if self._skill_registry is None:
            self._skill_registry = skills.SkillRegistry(
                project_root=self._project_root,
                plugins=self._plugins,
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

    def _apply_hook_injections(
        self,
        hook_injections: list[tuple[str, str]] | None,
        injections_list: list[ContextInjection],
    ) -> tuple[list[str], list[str]]:
        """
        Apply hook injections to prepend/append lists.

        Args:
            hook_injections: List of (content, location) tuples from hooks.
            injections_list: Mutable list to append ContextInjection records to.

        Returns:
            Tuple of (prepend_parts, append_parts) from hooks.
        """
        prepend: list[str] = []
        append: list[str] = []

        if not hook_injections:
            return prepend, append

        for content, location in hook_injections:
            injection = ContextInjection(
                source="hook",
                location=f"system_prompt_{location}",
                content=content,
                origin="context_build",
            )
            injections_list.append(injection)

            if self._logger:
                self._logger.log_context_injection(
                    source="hook",
                    location=f"system_prompt_{location}",
                    content=content,
                    origin="context_build",
                    trigger_type="hook",
                )

            if location == "prepend":
                prepend.append(content)
            else:
                append.append(content)

        return prepend, append

    def build(
        self,
        base_system_prompt: str,
        *,
        hook_injections: list[tuple[str, str]] | None = None,
    ) -> ConversationContext:
        """
        Build the complete conversation context.

        Args:
            base_system_prompt: The base system prompt to enhance.
            hook_injections: Optional list of (content, location) tuples from
                CONTEXT_BUILD hook results. Use build_async() for automatic
                hook firing, or call fire_context_build_hook() manually.

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

        # 4. Apply hook injections if provided (from async build)
        hook_prepend, hook_append = self._apply_hook_injections(
            hook_injections, injections
        )
        if hook_prepend:
            prepend_parts.extend(hook_prepend)
        if hook_append:
            append_parts.extend(hook_append)

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
            skill_registry=self._skill_registry,
        )

    def get_skill_registry(self) -> skills.SkillRegistry:
        """Get the skill registry for runtime skill triggering."""
        return self._get_skill_registry()

    async def fire_context_build_hook(
        self,
        base_system_prompt: str,
        injections_so_far: list[ContextInjection],
    ) -> list[tuple[str, str]]:
        """
        Fire the CONTEXT_BUILD hook and collect injections.

        Args:
            base_system_prompt: The base prompt being built.
            injections_so_far: List of injections already applied.

        Returns:
            List of (content, location) tuples from hook results.
            location is "prepend" or "append".
        """
        if not self._hook_manager:
            return []

        # Convert injections to serializable format
        injections_dict = [
            {
                "source": inj.source,
                "location": inj.location,
                "content": inj.content,
                "origin": inj.origin,
            }
            for inj in injections_so_far
        ]

        context = hooks_events.HookContext(
            event=hooks_events.HookEvent.CONTEXT_BUILD,
            session_id=self._session_id,
            cwd=self._project_root,
            base_system_prompt=base_system_prompt,
            injections_so_far=injections_dict,
            logger=self._logger,
        )

        result = await self._hook_manager.dispatch(
            hooks_events.HookEvent.CONTEXT_BUILD,
            context,
        )

        # Collect injections from hook result
        hook_injections: list[tuple[str, str]] = []
        if result.context_injection:
            location = result.context_location or "append"
            hook_injections.append((result.context_injection, location))

        return hook_injections

    async def build_async(self, base_system_prompt: str) -> ConversationContext:
        """
        Build the conversation context with async hook firing.

        This method fires the CONTEXT_BUILD hook to allow plugins to inject
        content into the system prompt.

        Args:
            base_system_prompt: The base system prompt to enhance.

        Returns:
            ConversationContext with the final system prompt and metadata.
        """
        # First do synchronous build steps to collect initial injections
        # We need to peek at what injections will be done
        temp_injections: list[ContextInjection] = []

        # Collect rules injection info
        if self._include_rules:
            rules_content = self._get_rules_manager().get_rules_for_prompt()
            if rules_content:
                temp_injections.append(ContextInjection(
                    source="rules",
                    location="system_prompt_prepend",
                    content=rules_content,
                    origin=str(self._project_root),
                ))

        # Collect profile injection info
        profile = self._resolve_profile()
        if profile:
            if profile.system_prompt_prefix:
                temp_injections.append(ContextInjection(
                    source="profile",
                    location="system_prompt_prepend",
                    content=profile.system_prompt_prefix,
                    origin=profile.name,
                ))
            if profile.system_prompt_suffix:
                temp_injections.append(ContextInjection(
                    source="profile",
                    location="system_prompt_append",
                    content=profile.system_prompt_suffix,
                    origin=profile.name,
                ))

        # Collect skills injection info
        if self._include_skills:
            skill_metadata = self._get_skill_registry().get_metadata_for_prompt()
            if skill_metadata:
                temp_injections.append(ContextInjection(
                    source="skill_metadata",
                    location="system_prompt_append",
                    content=skill_metadata,
                    origin="all_skills",
                ))

        # Fire the hook with current state
        hook_injections = await self.fire_context_build_hook(
            base_system_prompt, temp_injections
        )

        # Now do the full build with hook injections
        return self.build(base_system_prompt, hook_injections=hook_injections)


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

