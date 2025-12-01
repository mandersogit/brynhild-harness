"""Tests for core/prompts.py."""

import brynhild.config as config
import brynhild.core.prompts as prompts
import brynhild.tools as tools


class TestSystemPrompt:
    """Tests for system prompt generation."""

    def test_get_system_prompt_substitutes_model(self) -> None:
        """get_system_prompt substitutes the model name."""
        settings = config.Settings()
        registry = tools.build_registry_from_settings(settings)

        result = prompts.get_system_prompt("test-model-123", registry)

        assert "test-model-123" in result
        assert "{model_name}" not in result

    def test_prompt_mentions_brynhild(self) -> None:
        """Prompt identifies as Brynhild."""
        settings = config.Settings()
        registry = tools.build_registry_from_settings(settings)

        result = prompts.get_system_prompt("test-model", registry)

        assert "Brynhild" in result

    def test_prompt_mentions_tools(self) -> None:
        """Prompt mentions available tools."""
        settings = config.Settings()
        registry = tools.build_registry_from_settings(settings)

        result = prompts.get_system_prompt("test-model", registry)

        assert "- Inspect:" in result
        assert "- Bash:" in result
        assert "- Read:" in result

    def test_prompt_includes_bash_guidance_when_bash_available(self) -> None:
        """Prompt includes Bash-vs-Inspect guidance when both are available."""
        settings = config.Settings()
        registry = tools.build_registry_from_settings(settings)

        result = prompts.get_system_prompt("test-model", registry)

        assert "use Inspect instead of Bash" in result

    def test_empty_registry_produces_no_tools_message(self) -> None:
        """Empty registry produces 'no tools available' message."""
        registry = tools.ToolRegistry()

        result = prompts.get_system_prompt("test-model", registry)

        assert "no tools available" in result.lower()
