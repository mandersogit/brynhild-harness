"""
Tests for model profiles.
"""

import brynhild.profiles as profiles
import brynhild.profiles.builtin as builtin


class TestModelProfile:
    """Tests for the ModelProfile dataclass."""

    def test_create_basic_profile(self) -> None:
        """Can create a basic profile."""
        profile = profiles.ModelProfile(
            name="test-model",
            family="test",
            description="Test profile",
        )

        assert profile.name == "test-model"
        assert profile.family == "test"
        assert profile.description == "Test profile"
        assert profile.default_temperature == 0.7
        assert profile.supports_tools is True

    def test_get_enabled_patterns_text(self) -> None:
        """Can get concatenated enabled patterns."""
        profile = profiles.ModelProfile(
            name="test",
            prompt_patterns={
                "pattern1": "Content 1",
                "pattern2": "Content 2",
                "pattern3": "Content 3",
            },
            enabled_patterns=["pattern1", "pattern3"],
        )

        text = profile.get_enabled_patterns_text()
        assert "Content 1" in text
        assert "Content 3" in text
        assert "Content 2" not in text

    def test_build_system_prompt(self) -> None:
        """Can build full system prompt with patterns."""
        profile = profiles.ModelProfile(
            name="test",
            system_prompt_prefix="PREFIX",
            system_prompt_suffix="SUFFIX",
            prompt_patterns={
                "pattern1": "PATTERN1",
            },
            enabled_patterns=["pattern1"],
        )

        result = profile.build_system_prompt("BASE PROMPT")

        assert "PREFIX" in result
        assert "PATTERN1" in result
        assert "BASE PROMPT" in result
        assert "SUFFIX" in result
        # Check order
        assert result.index("PREFIX") < result.index("PATTERN1")
        assert result.index("PATTERN1") < result.index("BASE PROMPT")
        assert result.index("BASE PROMPT") < result.index("SUFFIX")

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """Can serialize and deserialize profile."""
        original = profiles.ModelProfile(
            name="test",
            family="test-family",
            description="Test description",
            default_temperature=0.5,
            prompt_patterns={"p1": "content"},
            enabled_patterns=["p1"],
        )

        data = original.to_dict()
        restored = profiles.ModelProfile.from_dict(data)

        assert restored.name == original.name
        assert restored.family == original.family
        assert restored.description == original.description
        assert restored.default_temperature == original.default_temperature
        assert restored.prompt_patterns == original.prompt_patterns
        assert restored.enabled_patterns == original.enabled_patterns


class TestProfileManager:
    """Tests for ProfileManager."""

    def test_loads_builtin_profiles(self) -> None:
        """Manager loads builtin profiles."""
        manager = profiles.ProfileManager(load_user_profiles=False)

        profile_names = [p.name for p in manager.list_profiles()]
        assert "default" in profile_names
        assert "gpt-oss-120b" in profile_names

    def test_resolve_exact_match(self) -> None:
        """Resolves exact profile name match."""
        manager = profiles.ProfileManager(load_user_profiles=False)

        profile = manager.resolve("gpt-oss-120b")
        assert profile.name == "gpt-oss-120b"

    def test_resolve_with_colon(self) -> None:
        """Resolves Ollama-format model names with colon (legacy compatibility)."""
        manager = profiles.ProfileManager(load_user_profiles=False)

        # Users may pass Ollama-native format; profile resolver should handle it
        profile = manager.resolve("gpt-oss:120b")
        assert profile.name == "gpt-oss-120b"

    def test_resolve_family_match(self) -> None:
        """Resolves by family prefix when no exact match."""
        manager = profiles.ProfileManager(load_user_profiles=False)

        # gpt-oss-120b has family="gpt-oss", so gpt-oss-unknown should match it
        profile = manager.resolve("gpt-oss-unknown-variant")
        assert profile.family == "gpt-oss"

    def test_resolve_falls_back_to_default(self) -> None:
        """Falls back to default for unknown models."""
        manager = profiles.ProfileManager(load_user_profiles=False)

        profile = manager.resolve("completely-unknown-model")
        assert profile.name == "default"

    def test_register_profile(self) -> None:
        """Can register a custom profile."""
        manager = profiles.ProfileManager(load_user_profiles=False)

        custom = profiles.ModelProfile(name="custom-test", description="Custom")
        manager.register_profile(custom)

        profile = manager.resolve("custom-test")
        assert profile.name == "custom-test"
        assert profile.description == "Custom"


class TestBuiltinProfiles:
    """Tests for builtin profile definitions."""

    def test_gpt_oss_120b_has_required_patterns(self) -> None:
        """GPT-OSS-120B profile has essential patterns."""
        profile = builtin.GPT_OSS_120B

        assert "persistence" in profile.prompt_patterns
        assert "context_gathering" in profile.prompt_patterns
        assert "tool_policy" in profile.prompt_patterns
        assert "coding" in profile.prompt_patterns

    def test_gpt_oss_120b_patterns_enabled(self) -> None:
        """GPT-OSS-120B profile has patterns enabled."""
        profile = builtin.GPT_OSS_120B

        assert "persistence" in profile.enabled_patterns
        assert "coding" in profile.enabled_patterns

    def test_gpt_oss_120b_fast_is_lighter(self) -> None:
        """GPT-OSS-120B-FAST has fewer patterns and lower limits."""
        full = builtin.GPT_OSS_120B
        fast = builtin.GPT_OSS_120B_FAST

        assert len(fast.enabled_patterns) < len(full.enabled_patterns)
        assert fast.max_tools_per_turn < full.max_tools_per_turn  # type: ignore
        assert fast.thoroughness == "fast"
        assert full.thoroughness == "thorough"

    def test_all_profiles_have_required_fields(self) -> None:
        """All builtin profiles have required fields."""
        for profile in builtin.get_all_profiles():
            assert profile.name
            assert profile.default_temperature > 0
            assert profile.default_max_tokens > 0

