"""Tests for LLM API providers."""

import os as _os
import unittest.mock as _mock

import pytest as _pytest

import brynhild.api as api


class TestProviderFactory:
    """Tests for provider factory functions."""

    def test_get_available_providers_returns_list(self) -> None:
        """get_available_providers should return a list of provider info."""
        providers = api.get_available_providers()
        assert isinstance(providers, list)
        # OpenRouter is available, plus planned providers (ollama, vllm, vertex)
        assert len(providers) >= 1

        # Check structure
        for p in providers:
            assert "name" in p
            assert "description" in p
            assert "key_env_var" in p or p["key_env_var"] is None  # ollama has no key
            assert "key_configured" in p
            assert "available" in p

    def test_get_available_providers_includes_openrouter(self) -> None:
        """OpenRouter should be in the available providers list."""
        providers = api.get_available_providers()
        names = [p["name"] for p in providers]
        assert "openrouter" in names

    def test_get_default_provider_with_openrouter_key(self) -> None:
        """With OPENROUTER_API_KEY set, default provider should be openrouter."""
        clean_env = {k: v for k, v in _os.environ.items() if not k.endswith("_API_KEY")}
        clean_env.pop("BRYNHILD_PROVIDER", None)
        with _mock.patch.dict(_os.environ, clean_env, clear=True):
            _os.environ["OPENROUTER_API_KEY"] = "test-key"
            provider = api.get_default_provider()
            assert provider == "openrouter"

    def test_get_default_provider_with_explicit_setting(self) -> None:
        """BRYNHILD_PROVIDER should override auto-detection."""
        with _mock.patch.dict(
            _os.environ,
            {"BRYNHILD_PROVIDER": "openrouter", "OPENROUTER_API_KEY": "test-key"},
            clear=False,
        ):
            provider = api.get_default_provider()
            assert provider == "openrouter"

    def test_get_default_provider_from_config(self) -> None:
        """Without env vars, get_default_provider should return config default."""
        clean_env = {
            k: v
            for k, v in _os.environ.items()
            if not k.endswith("_API_KEY") and k != "BRYNHILD_PROVIDER"
        }
        with _mock.patch.dict(_os.environ, clean_env, clear=True):
            provider = api.get_default_provider()
            # Config file has providers.default: openrouter
            assert provider == "openrouter"

    def test_create_provider_openrouter(self) -> None:
        """create_provider should create OpenRouterProvider for 'openrouter'."""
        with _mock.patch.dict(_os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=False):
            provider = api.create_provider(provider="openrouter")
            assert provider.name == "openrouter"

    def test_create_provider_with_custom_model(self) -> None:
        """create_provider should use custom model when specified."""
        with _mock.patch.dict(_os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=False):
            provider = api.create_provider(provider="openrouter", model="openai/gpt-4o")
            assert provider.model == "openai/gpt-4o"

    def test_create_provider_raises_for_missing_key(self) -> None:
        """create_provider should raise ValueError when API key is missing."""
        clean_env = {k: v for k, v in _os.environ.items() if not k.endswith("_API_KEY")}
        clean_env.pop("BRYNHILD_PROVIDER", None)
        with (
            _mock.patch.dict(_os.environ, clean_env, clear=True),
            _pytest.raises(ValueError, match="OPENROUTER_API_KEY"),
        ):
            api.create_provider(provider="openrouter")

    def test_create_provider_raises_for_unknown_provider(self) -> None:
        """create_provider should raise ValueError for unknown provider."""
        with _pytest.raises(ValueError, match="Unknown provider"):
            api.create_provider(provider="unknown")


class TestStreamEvent:
    """Tests for StreamEvent type."""

    def test_stream_event_text_delta(self) -> None:
        """StreamEvent should store text delta."""
        event = api.StreamEvent(type="text_delta", text="Hello")
        assert event.type == "text_delta"
        assert event.text == "Hello"

    def test_stream_event_tool_use(self) -> None:
        """StreamEvent should store tool use info."""
        tool_use = api.ToolUse(id="123", name="Bash", input={"command": "ls"})
        event = api.StreamEvent(type="tool_use_start", tool_use=tool_use)
        assert event.type == "tool_use_start"
        assert event.tool_use is not None
        assert event.tool_use.name == "Bash"


class TestUsage:
    """Tests for Usage type."""

    def test_usage_total_tokens(self) -> None:
        """Usage.total_tokens should sum input and output."""
        usage = api.Usage(input_tokens=100, output_tokens=50)
        assert usage.total_tokens == 150


class TestTool:
    """Tests for Tool type."""

    def test_tool_to_anthropic_format(self) -> None:
        """Tool should convert to Anthropic API format."""
        tool = api.Tool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}},
        )
        formatted = tool.to_anthropic_format()
        assert formatted["name"] == "test_tool"
        assert formatted["description"] == "A test tool"
        assert "input_schema" in formatted

    def test_tool_to_openai_format(self) -> None:
        """Tool should convert to OpenAI/OpenRouter format."""
        tool = api.Tool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}},
        )
        formatted = tool.to_openai_format()
        assert formatted["type"] == "function"
        assert formatted["function"]["name"] == "test_tool"
        assert formatted["function"]["description"] == "A test tool"
        assert "parameters" in formatted["function"]


class TestCompletionResponse:
    """Tests for CompletionResponse type."""

    def test_completion_response_has_tool_use(self) -> None:
        """has_tool_use should return True when tool_uses is not empty."""
        response = api.CompletionResponse(
            id="123",
            content="",
            stop_reason="tool_use",
            usage=api.Usage(input_tokens=10, output_tokens=5),
            tool_uses=[api.ToolUse(id="1", name="Bash", input={})],
        )
        assert response.has_tool_use is True

    def test_completion_response_no_tool_use(self) -> None:
        """has_tool_use should return False when tool_uses is empty."""
        response = api.CompletionResponse(
            id="123",
            content="Hello",
            stop_reason="end_turn",
            usage=api.Usage(input_tokens=10, output_tokens=5),
        )
        assert response.has_tool_use is False


# Mark live tests that require actual API keys
@_pytest.mark.live
class TestOpenRouterProviderLive:
    """Live tests for OpenRouter provider (requires OPENROUTER_API_KEY)."""

    @_pytest.fixture
    def provider(self):
        """Create OpenRouter provider if API key is available."""
        api_key = _os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            _pytest.skip("OPENROUTER_API_KEY not set")
        import brynhild.api.openrouter_provider as openrouter_provider

        return openrouter_provider.OpenRouterProvider(
            api_key=api_key,
            # Use free model with tools support that respects data policy
            model="openai/gpt-oss-20b",
        )

    @_pytest.mark.asyncio
    async def test_complete_simple_message(self, provider) -> None:
        """Provider should complete a simple message."""
        # Note: olmo-3-32b-think is a thinking-first model that may use all
        # output tokens on reasoning before producing content. We verify that
        # the model produced SOMETHING (either content or thinking trace).
        response = await provider.complete(
            messages=[{"role": "user", "content": "Say 'hello' and nothing else."}],
            max_tokens=512,
        )
        # Model should produce either content or thinking (or both)
        has_output = len(response.content) > 0 or (
            response.thinking is not None and len(response.thinking) > 0
        )
        assert has_output, "Model produced neither content nor thinking"
        assert response.usage.input_tokens > 0

