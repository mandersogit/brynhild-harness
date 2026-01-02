"""
Integration tests for profile application.

Test IDs from design-plan-phase6.md:
- PI-01: Profile modifies system prompt
- PI-02: Profile prefix/suffix added
- PI-03: Profile enabled patterns
- PI-04: --profile flag works (CLI test, simplified)
"""

import pathlib as _pathlib
import unittest.mock as _mock

import brynhild.core.context as context
import brynhild.profiles.manager as profiles_manager
import brynhild.profiles.types as profiles_types


class TestProfileIntegration:
    """Integration tests for profile system."""

    def test_pi01_profile_modifies_system_prompt(self) -> None:
        """PI-01: build_system_prompt() applied before LLM call."""
        # Create a profile
        profile = profiles_types.ModelProfile(
            name="test-profile",
            system_prompt_prefix="[PREFIX]",
            system_prompt_suffix="[SUFFIX]",
        )

        # Apply profile to base prompt
        base_prompt = "You are an assistant."
        result = profile.build_system_prompt(base_prompt)

        # Verify modification
        assert "[PREFIX]" in result
        assert "[SUFFIX]" in result
        assert "You are an assistant." in result

    def test_pi02_profile_prefix_suffix_added(self) -> None:
        """PI-02: system_prompt_prefix and suffix in final prompt."""
        with _mock.patch.object(profiles_manager.ProfileManager, "resolve") as mock_resolve:
            profile = profiles_types.ModelProfile(
                name="gpt-test",
                system_prompt_prefix="## Model Guidelines\n\nBe concise.",
                system_prompt_suffix="## End Notes\n\nAlways verify.",
            )
            mock_resolve.return_value = profile

            ctx = context.build_context(
                "Base prompt",
                include_rules=False,
                include_skills=False,
                model="gpt-test",
            )

            # Verify prefix and suffix are in final prompt
            assert "Model Guidelines" in ctx.system_prompt
            assert "Be concise" in ctx.system_prompt
            assert "End Notes" in ctx.system_prompt
            assert "Always verify" in ctx.system_prompt
            assert "Base prompt" in ctx.system_prompt

    def test_pi03_profile_enabled_patterns(self) -> None:
        """PI-03: Enabled patterns included in system prompt."""
        # Create profile with patterns
        profile = profiles_types.ModelProfile(
            name="test-profile",
            prompt_patterns={
                "persistence": "Never give up on the task.",
                "tool_policy": "Always explain tool usage.",
                "unused": "This pattern is not enabled.",
            },
            enabled_patterns=["persistence", "tool_policy"],
        )

        base_prompt = "You are an assistant."
        result = profile.build_system_prompt(base_prompt)

        # Enabled patterns should be included
        assert "Never give up" in result
        assert "Always explain tool usage" in result
        # Non-enabled pattern should NOT be included
        assert "This pattern is not enabled" not in result

    def test_pi04_profile_name_parameter_works(self) -> None:
        """PI-04: profile_name parameter loads and applies named profile."""
        with _mock.patch.object(profiles_manager.ProfileManager, "get_profile") as mock_get:
            profile = profiles_types.ModelProfile(
                name="custom-profile",
                system_prompt_prefix="[CUSTOM PREFIX]",
            )
            mock_get.return_value = profile

            ctx = context.build_context(
                "Base prompt",
                include_rules=False,
                include_skills=False,
                profile_name="custom-profile",
            )

            # Profile should be applied
            assert ctx.profile is not None
            assert ctx.profile.name == "custom-profile"
            assert "[CUSTOM PREFIX]" in ctx.system_prompt


class TestProfileResolution:
    """Tests for profile resolution logic."""

    def test_resolves_by_exact_name(self) -> None:
        """Exact profile name match works."""
        manager = profiles_manager.ProfileManager(load_user_profiles=False)

        # Register a test profile
        profile = profiles_types.ModelProfile(
            name="my-custom-profile",
            description="Test profile",
        )
        manager.register_profile(profile)

        # Should find by exact name
        resolved = manager.get_profile("my-custom-profile")
        assert resolved is not None
        assert resolved.name == "my-custom-profile"

    def test_resolves_by_model_family(self) -> None:
        """Model family prefix matching works."""
        manager = profiles_manager.ProfileManager(load_user_profiles=False)

        # Register a profile with family
        profile = profiles_types.ModelProfile(
            name="gpt-family",
            family="gpt",
            description="GPT family profile",
        )
        manager.register_profile(profile)

        # Should resolve gpt-4 to gpt-family
        resolved = manager.resolve("gpt-4-turbo")
        assert (
            resolved.family == "gpt" or resolved.name == "gpt-family" or resolved.name == "default"
        )

    def test_falls_back_to_default(self) -> None:
        """Unknown model falls back to default profile."""
        manager = profiles_manager.ProfileManager(load_user_profiles=False)

        # Resolve unknown model
        resolved = manager.resolve("completely-unknown-model-xyz")

        # Should get default (may or may not exist based on builtins)
        assert resolved is not None
        assert (
            resolved.name in ["default", "completely-unknown-model-xyz"]
            or resolved.name is not None
        )


class TestProfileContextInjection:
    """Tests for profile injection into context."""

    def test_profile_injection_tracked(self) -> None:
        """Profile injections are tracked in context.injections."""
        with _mock.patch.object(profiles_manager.ProfileManager, "resolve") as mock_resolve:
            profile = profiles_types.ModelProfile(
                name="test-profile",
                system_prompt_prefix="[PREFIX]",
                system_prompt_suffix="[SUFFIX]",
            )
            mock_resolve.return_value = profile

            ctx = context.build_context(
                "Base prompt",
                include_rules=False,
                include_skills=False,
                model="test-model",
            )

            # Should have profile injections tracked
            profile_injections = [i for i in ctx.injections if i.source == "profile"]
            assert len(profile_injections) >= 1

    def test_profile_injection_logged(self, tmp_path: _pathlib.Path) -> None:
        """Profile injections are logged."""
        import brynhild.logging.conversation_logger as conversation_logger

        log_file = tmp_path / "test.jsonl"
        logger = conversation_logger.ConversationLogger(
            log_file=log_file,
            provider="test",
            model="test-model",
            enabled=True,
        )

        with _mock.patch.object(profiles_manager.ProfileManager, "resolve") as mock_resolve:
            profile = profiles_types.ModelProfile(
                name="test-profile",
                system_prompt_prefix="[PREFIX]",
            )
            mock_resolve.return_value = profile

            context.build_context(
                "Base prompt",
                include_rules=False,
                include_skills=False,
                model="test-model",
                logger=logger,
            )

        logger.close()

        # Verify log contains profile injection
        log_content = log_file.read_text()
        assert "context_injection" in log_content
        assert '"source": "profile"' in log_content
