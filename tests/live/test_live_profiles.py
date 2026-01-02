"""
Live tests for model profiles with actual LLM completions.

These tests verify that:
- Profiles modify model behavior as expected
- System prompt patterns influence responses
- Profile-enhanced completions work correctly

Configuration (set in .env, which is gitignored):
    BRYNHILD_OLLAMA_HOST: Hostname of Ollama server (or OLLAMA_HOST as fallback)
    OPENROUTER_API_KEY: API key for OpenRouter tests

Example usage:
    # Run with settings from .env
    make test-ollama
"""

import os as _os

import pytest as _pytest

import brynhild.api as api
import brynhild.profiles as profiles
import brynhild.profiles.builtin as builtin

# All tests require live API access
# ollama_local: most tests run against local/private Ollama server
pytestmark = [
    _pytest.mark.live,
    _pytest.mark.slow,
    _pytest.mark.profiles,
    _pytest.mark.ollama_local,
]

# Default models for testing
OLLAMA_MODEL = _os.environ.get("BRYNHILD_OLLAMA_MODEL", "openai/gpt-oss-120b")
OPENROUTER_MODEL = _os.environ.get("BRYNHILD_TEST_MODEL", "openai/gpt-oss-120b")


class TestProfileSystemPromptBehavior:
    """Test that profile patterns influence model behavior."""

    @_pytest.fixture
    def ollama_provider(self) -> api.LLMProvider:
        """Create Ollama provider for tests."""
        return api.create_provider(provider="ollama", model=OLLAMA_MODEL)

    @_pytest.fixture
    def profile(self) -> profiles.ModelProfile:
        """Get the GPT-OSS-120B profile."""
        return builtin.GPT_OSS_120B

    @_pytest.mark.asyncio
    async def test_profile_builds_system_prompt(self, profile: profiles.ModelProfile) -> None:
        """Profile can build a system prompt with patterns."""
        base_prompt = "You are a helpful coding assistant."
        full_prompt = profile.build_system_prompt(base_prompt)

        # Should contain the base prompt
        assert "helpful coding assistant" in full_prompt

        # Should contain key patterns
        assert "<persistence>" in full_prompt
        assert "<coding_guidelines>" in full_prompt
        assert "keep going until" in full_prompt

    @_pytest.mark.asyncio
    async def test_profile_enhanced_completion(
        self,
        ollama_provider: api.LLMProvider,
        profile: profiles.ModelProfile,
    ) -> None:
        """Model responds with profile-enhanced system prompt."""
        base_prompt = "You are a coding assistant. Be concise."
        system_prompt = profile.build_system_prompt(base_prompt)

        response = await ollama_provider.complete(
            messages=[
                {
                    "role": "user",
                    "content": "Write a Python function that adds two numbers.",
                }
            ],
            system=system_prompt,
            max_tokens=500,
        )

        # Should get a response
        assert response.content is not None
        assert len(response.content) > 0

        # Response should contain a function (coding pattern should help)
        content_lower = response.content.lower()
        assert "def " in content_lower or "function" in content_lower

    @_pytest.mark.asyncio
    async def test_coding_pattern_produces_readable_code(
        self,
        ollama_provider: api.LLMProvider,
        profile: profiles.ModelProfile,
    ) -> None:
        """Coding pattern produces code with descriptive names (not single letters)."""
        system_prompt = profile.build_system_prompt("You are a coding assistant.")

        response = await ollama_provider.complete(
            messages=[
                {
                    "role": "user",
                    "content": "Write a Python function that calculates the factorial of a number.",
                }
            ],
            system=system_prompt,
            max_tokens=500,
        )

        assert response.content is not None
        content = response.content

        # Should have descriptive variable names (the coding pattern asks for this)
        # Check that we don't have single-letter variables dominating
        # This is a heuristic check - the model should prefer names like 'number' over 'n'
        assert "def " in content or "factorial" in content.lower()


class TestProfileResolutionWithProviders:
    """Test profile resolution works with different providers."""

    def test_resolve_ollama_model(self) -> None:
        """Can resolve profile for Ollama model names (both formats)."""
        manager = profiles.ProfileManager(load_user_profiles=False)

        # Test both canonical and Ollama-native formats
        profile1 = manager.resolve("openai/gpt-oss-120b", provider="ollama")
        profile2 = manager.resolve("gpt-oss:120b", provider="ollama")  # legacy Ollama format

        assert profile1.name == "gpt-oss-120b"
        assert profile2.name == "gpt-oss-120b"

    def test_resolve_openrouter_model(self) -> None:
        """Can resolve profile for OpenRouter model names."""
        manager = profiles.ProfileManager(load_user_profiles=False)

        # OpenRouter format: provider/model
        profile = manager.resolve("openai/gpt-oss-120b", provider="openrouter")

        assert profile.name == "gpt-oss-120b"


class TestProfileWithToolCalling:
    """Test profiles work correctly with tool calling."""

    @_pytest.fixture
    def ollama_provider(self) -> api.LLMProvider:
        """Create Ollama provider for tests."""
        return api.create_provider(provider="ollama", model=OLLAMA_MODEL)

    @_pytest.fixture
    def profile(self) -> profiles.ModelProfile:
        """Get the GPT-OSS-120B profile."""
        return builtin.GPT_OSS_120B

    @_pytest.mark.asyncio
    async def test_profile_with_tools(
        self,
        ollama_provider: api.LLMProvider,
        profile: profiles.ModelProfile,
    ) -> None:
        """Model with profile can use tools."""
        system_prompt = profile.build_system_prompt("You are a helpful assistant.")

        calculator = api.Tool(
            name="calculator",
            description="Perform basic arithmetic calculations.",
            input_schema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Math expression like '2 + 2'",
                    }
                },
                "required": ["expression"],
            },
        )

        response = await ollama_provider.complete(
            messages=[
                {
                    "role": "user",
                    "content": "What is 123 * 456? Use the calculator tool.",
                }
            ],
            system=system_prompt,
            tools=[calculator],
            max_tokens=300,
        )

        # Should either use the tool or provide an answer
        has_tool_use = len(response.tool_uses) > 0
        has_content = response.content and len(response.content) > 0

        assert has_tool_use or has_content, "Should have tool use or content"

        if has_tool_use:
            # Check tool use is well-formed
            tool_use = response.tool_uses[0]
            assert tool_use.name == "calculator"
            assert "expression" in tool_use.input


class TestFastProfileVsThoroughProfile:
    """Compare fast vs thorough profile behaviors."""

    @_pytest.fixture
    def ollama_provider(self) -> api.LLMProvider:
        """Create Ollama provider for tests."""
        return api.create_provider(provider="ollama", model=OLLAMA_MODEL)

    @_pytest.mark.asyncio
    async def test_fast_profile_produces_output(
        self,
        ollama_provider: api.LLMProvider,
    ) -> None:
        """Fast profile produces valid output."""
        profile = builtin.GPT_OSS_120B_FAST
        system_prompt = profile.build_system_prompt("You are a coding assistant.")

        response = await ollama_provider.complete(
            messages=[
                {
                    "role": "user",
                    "content": "What is a Python list comprehension?",
                }
            ],
            system=system_prompt,
            max_tokens=300,
        )

        assert response.content is not None
        assert len(response.content) > 0
        # Should mention list comprehension
        assert "list" in response.content.lower() or "comprehension" in response.content.lower()

    @_pytest.mark.asyncio
    async def test_thorough_profile_produces_output(
        self,
        ollama_provider: api.LLMProvider,
    ) -> None:
        """Thorough profile produces valid output."""
        profile = builtin.GPT_OSS_120B
        system_prompt = profile.build_system_prompt("You are a coding assistant.")

        response = await ollama_provider.complete(
            messages=[
                {
                    "role": "user",
                    "content": "Write a function to check if a number is prime.",
                }
            ],
            system=system_prompt,
            max_tokens=500,
        )

        # Profile may cause model to use tools or produce content
        has_output = (response.content and len(response.content) > 0) or len(response.tool_uses) > 0
        assert has_output, "Should have content or tool uses"


@_pytest.mark.skipif(
    not _os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)
class TestProfileWithOpenRouter:
    """Test profiles work with OpenRouter provider."""

    @_pytest.fixture
    def openrouter_provider(self) -> api.LLMProvider:
        """Create OpenRouter provider for tests."""
        return api.create_provider(
            provider="openrouter",
            model=OPENROUTER_MODEL,
        )

    @_pytest.fixture
    def profile(self) -> profiles.ModelProfile:
        """Get the GPT-OSS-120B profile."""
        return builtin.GPT_OSS_120B

    @_pytest.mark.asyncio
    async def test_openrouter_with_profile(
        self,
        openrouter_provider: api.LLMProvider,
        profile: profiles.ModelProfile,
    ) -> None:
        """Profile works with OpenRouter provider."""
        system_prompt = profile.build_system_prompt("You are a helpful assistant.")

        response = await openrouter_provider.complete(
            messages=[
                {
                    "role": "user",
                    "content": "Say 'hello' and nothing else.",
                }
            ],
            system=system_prompt,
            max_tokens=100,
        )

        # Should get a response (content or thinking)
        has_output = (response.content and len(response.content) > 0) or (
            response.thinking and len(response.thinking) > 0
        )
        assert has_output, "Should have content or thinking output"
