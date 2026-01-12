"""Tests for LLM API providers."""

import os as _os
import unittest.mock as _mock

import pytest as _pytest

import brynhild.api as api
import brynhild.api.base as base


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

    def test_no_provider_error_is_provider_agnostic(self) -> None:
        """Error when no provider configured should not mention specific provider."""
        # Clean environment of all API keys and provider settings
        clean_env = {
            k: v
            for k, v in _os.environ.items()
            if not k.endswith("_API_KEY")
            and not k.startswith("BRYNHILD_PROVIDER")
        }

        # Mock Settings to have no default provider
        mock_settings = _mock.MagicMock()
        mock_settings.providers.default = None

        with (
            _mock.patch.dict(_os.environ, clean_env, clear=True),
            _mock.patch("brynhild.config.Settings", return_value=mock_settings),
            _pytest.raises(ValueError) as exc_info,
        ):
            api.create_provider()

        error_msg = str(exc_info.value)
        # Should NOT mention specific provider API keys
        assert "OPENROUTER_API_KEY" not in error_msg
        # Should be generic and helpful
        assert "No provider configured" in error_msg
        assert "Available:" in error_msg


class TestModelAliasResolution:
    """Tests for model alias resolution in create_provider."""

    def test_model_alias_resolved(self, monkeypatch: _pytest.MonkeyPatch) -> None:
        """Model alias should be resolved before provider creation."""
        # Set up config with alias via env var
        monkeypatch.setenv("BRYNHILD_MODELS__ALIASES__short", "actual/full-model-name")
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

        provider = api.create_provider(provider="openrouter", model="short")
        # The alias should have been resolved
        assert provider.model == "actual/full-model-name"

    def test_unknown_model_passthrough(self, monkeypatch: _pytest.MonkeyPatch) -> None:
        """Unknown model names should pass through unchanged."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

        provider = api.create_provider(provider="openrouter", model="unknown-model")
        assert provider.model == "unknown-model"

    def test_model_alias_with_slash(self, monkeypatch: _pytest.MonkeyPatch) -> None:
        """Model alias with provider prefix should work."""
        monkeypatch.setenv(
            "BRYNHILD_MODELS__ALIASES__haiku", "anthropic/claude-haiku-4-5"
        )
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

        provider = api.create_provider(provider="openrouter", model="haiku")
        assert provider.model == "anthropic/claude-haiku-4-5"


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


class TestReasoningLevelBase:
    """Tests for ReasoningLevel type and LLMProvider helper methods."""

    def test_known_reasoning_levels_constant(self) -> None:
        """KNOWN_REASONING_LEVELS should include all standard values."""
        expected = frozenset({"auto", "off", "minimal", "low", "medium", "high", "maximum"})
        assert expected == base.KNOWN_REASONING_LEVELS

    def test_parse_reasoning_level_standard(self) -> None:
        """parse_reasoning_level should return (value, False) for standard values."""
        level, is_raw = base.parse_reasoning_level("high")
        assert level == "high"
        assert is_raw is False

    def test_parse_reasoning_level_raw_prefix(self) -> None:
        """parse_reasoning_level should strip raw: prefix and return True."""
        level, is_raw = base.parse_reasoning_level("raw:thinking_budget=65536")
        assert level == "thinking_budget=65536"
        assert is_raw is True

    def test_parse_reasoning_level_raw_prefix_simple(self) -> None:
        """parse_reasoning_level should work with simple raw values."""
        level, is_raw = base.parse_reasoning_level("raw:effort_high")
        assert level == "effort_high"
        assert is_raw is True

    def test_provider_default_reasoning_level(self) -> None:
        """LLMProvider.default_reasoning_level should return 'auto' by default."""
        with _mock.patch.dict(_os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=False):
            provider = api.create_provider(provider="openrouter")
            assert provider.default_reasoning_level == "auto"

    def test_provider_get_reasoning_level_default(self) -> None:
        """get_reasoning_level should return default when config is 'auto'."""
        with _mock.patch.dict(_os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=False):
            provider = api.create_provider(provider="openrouter")
            level = provider.get_reasoning_level()
            assert level == provider.default_reasoning_level

    def test_provider_get_reasoning_level_from_config(self) -> None:
        """get_reasoning_level should use config value when not 'auto'."""
        with _mock.patch.dict(
            _os.environ,
            {
                "OPENROUTER_API_KEY": "test-key",
                "BRYNHILD_BEHAVIOR__REASONING_LEVEL": "high",
            },
            clear=False,
        ):
            provider = api.create_provider(provider="openrouter")
            level = provider.get_reasoning_level()
            assert level == "high"

    def test_provider_get_reasoning_level_off(self) -> None:
        """get_reasoning_level should return 'off' when configured."""
        with _mock.patch.dict(
            _os.environ,
            {
                "OPENROUTER_API_KEY": "test-key",
                "BRYNHILD_BEHAVIOR__REASONING_LEVEL": "off",
            },
            clear=False,
        ):
            provider = api.create_provider(provider="openrouter")
            level = provider.get_reasoning_level()
            assert level == "off"

    def test_provider_get_reasoning_level_raw_strips_prefix(self) -> None:
        """get_reasoning_level should strip raw: prefix from custom values."""
        with _mock.patch.dict(
            _os.environ,
            {
                "OPENROUTER_API_KEY": "test-key",
                "BRYNHILD_BEHAVIOR__REASONING_LEVEL": "raw:vertex-ultra",
            },
            clear=False,
        ):
            provider = api.create_provider(provider="openrouter")
            level = provider.get_reasoning_level()
            assert level == "vertex-ultra"

    def test_provider_get_reasoning_level_unknown_warns(self) -> None:
        """get_reasoning_level should warn on unknown values without raw: prefix."""
        with _mock.patch.dict(
            _os.environ,
            {
                "OPENROUTER_API_KEY": "test-key",
                "BRYNHILD_BEHAVIOR__REASONING_LEVEL": "typo-value",
            },
            clear=False,
        ):
            provider = api.create_provider(provider="openrouter")
            with _mock.patch.object(base._logger, "warning") as mock_warn:
                level = provider.get_reasoning_level()
                assert level == "typo-value"
                mock_warn.assert_called_once()
                assert "typo-value" in str(mock_warn.call_args)
                assert "raw:" in str(mock_warn.call_args)

    def test_provider_get_reasoning_level_raw_no_warning(self) -> None:
        """get_reasoning_level should NOT warn on raw: prefixed values."""
        with _mock.patch.dict(
            _os.environ,
            {
                "OPENROUTER_API_KEY": "test-key",
                "BRYNHILD_BEHAVIOR__REASONING_LEVEL": "raw:custom-value",
            },
            clear=False,
        ):
            provider = api.create_provider(provider="openrouter")
            with _mock.patch.object(base._logger, "warning") as mock_warn:
                level = provider.get_reasoning_level()
                assert level == "custom-value"
                mock_warn.assert_not_called()

    def test_provider_translate_reasoning_level_base_returns_empty(self) -> None:
        """Base LLMProvider.translate_reasoning_level should return empty dict."""
        # Base class method returns {} - providers override with their own logic
        params = base.LLMProvider.translate_reasoning_level(None, "high")
        assert params == {}


class TestOpenRouterReasoningLevel:
    """Tests for OpenRouter reasoning level translation."""

    @_pytest.fixture
    def provider(self) -> api.LLMProvider:
        """Create OpenRouter provider with a reasoning-capable model."""
        with _mock.patch.dict(_os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=False):
            return api.create_provider(provider="openrouter", model="openai/gpt-oss-120b")

    @_pytest.fixture
    def non_reasoning_provider(self) -> api.LLMProvider:
        """Create OpenRouter provider with a model that doesn't support reasoning."""
        with _mock.patch.dict(_os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=False):
            return api.create_provider(provider="openrouter", model="anthropic/claude-haiku-4.5")

    def test_translate_auto_returns_empty(self, provider: api.LLMProvider) -> None:
        """auto level should return empty dict (let provider decide)."""
        params = provider.translate_reasoning_level("auto")
        assert params == {}

    def test_translate_off_to_none(self, provider: api.LLMProvider) -> None:
        """off level should map to effort: none."""
        params = provider.translate_reasoning_level("off")
        assert params == {"reasoning": {"effort": "none"}}

    def test_translate_minimal(self, provider: api.LLMProvider) -> None:
        """minimal level should map to effort: minimal."""
        params = provider.translate_reasoning_level("minimal")
        assert params == {"reasoning": {"effort": "minimal"}}

    def test_translate_low(self, provider: api.LLMProvider) -> None:
        """low level should map to effort: low."""
        params = provider.translate_reasoning_level("low")
        assert params == {"reasoning": {"effort": "low"}}

    def test_translate_medium(self, provider: api.LLMProvider) -> None:
        """medium level should map to effort: medium."""
        params = provider.translate_reasoning_level("medium")
        assert params == {"reasoning": {"effort": "medium"}}

    def test_translate_high(self, provider: api.LLMProvider) -> None:
        """high level should map to effort: high."""
        params = provider.translate_reasoning_level("high")
        assert params == {"reasoning": {"effort": "high"}}

    def test_translate_maximum_to_xhigh(self, provider: api.LLMProvider) -> None:
        """maximum level should map to effort: xhigh."""
        params = provider.translate_reasoning_level("maximum")
        assert params == {"reasoning": {"effort": "xhigh"}}

    def test_translate_raw_passthrough(self, provider: api.LLMProvider) -> None:
        """Raw values should be passed through as effort."""
        params = provider.translate_reasoning_level("raw:custom-effort")
        assert params == {"reasoning": {"effort": "custom-effort"}}

    def test_non_reasoning_model_returns_empty(
        self, non_reasoning_provider: api.LLMProvider
    ) -> None:
        """Non-reasoning models should return empty dict."""
        params = non_reasoning_provider.translate_reasoning_level("high")
        assert params == {}


class TestOllamaReasoningLevel:
    """Tests for Ollama reasoning level translation."""

    @_pytest.fixture
    def gpt_oss_provider(self) -> api.LLMProvider:
        """Create Ollama provider with a GPT-OSS model (string think levels)."""
        # Ollama doesn't require API key
        return api.create_provider(provider="ollama", model="gpt-oss-120b")

    @_pytest.fixture
    def deepseek_provider(self) -> api.LLMProvider:
        """Create Ollama provider with a DeepSeek R1 model (boolean think)."""
        return api.create_provider(provider="ollama", model="deepseek-r1:latest")

    @_pytest.fixture
    def non_reasoning_provider(self) -> api.LLMProvider:
        """Create Ollama provider with a model that doesn't support reasoning."""
        return api.create_provider(provider="ollama", model="llama3:latest")

    def test_gpt_oss_translate_auto_returns_empty(
        self, gpt_oss_provider: api.LLMProvider
    ) -> None:
        """auto level should return empty dict (let model decide)."""
        params = gpt_oss_provider.translate_reasoning_level("auto")
        assert params == {}

    def test_gpt_oss_translate_off_to_low(
        self, gpt_oss_provider: api.LLMProvider
    ) -> None:
        """off level should map to think: low (can't disable GPT-OSS thinking)."""
        params = gpt_oss_provider.translate_reasoning_level("off")
        assert params == {"think": "low"}

    def test_gpt_oss_translate_low(self, gpt_oss_provider: api.LLMProvider) -> None:
        """low level should map to think: low."""
        params = gpt_oss_provider.translate_reasoning_level("low")
        assert params == {"think": "low"}

    def test_gpt_oss_translate_medium(self, gpt_oss_provider: api.LLMProvider) -> None:
        """medium level should map to think: medium."""
        params = gpt_oss_provider.translate_reasoning_level("medium")
        assert params == {"think": "medium"}

    def test_gpt_oss_translate_high(self, gpt_oss_provider: api.LLMProvider) -> None:
        """high level should map to think: high."""
        params = gpt_oss_provider.translate_reasoning_level("high")
        assert params == {"think": "high"}

    def test_gpt_oss_translate_maximum(
        self, gpt_oss_provider: api.LLMProvider
    ) -> None:
        """maximum level should map to think: high (max available)."""
        params = gpt_oss_provider.translate_reasoning_level("maximum")
        assert params == {"think": "high"}

    def test_gpt_oss_raw_passthrough(self, gpt_oss_provider: api.LLMProvider) -> None:
        """Raw values should be passed through as think."""
        params = gpt_oss_provider.translate_reasoning_level("raw:custom")
        assert params == {"think": "custom"}

    def test_deepseek_translate_off_to_false(
        self, deepseek_provider: api.LLMProvider
    ) -> None:
        """off level should map to think: false for non-GPT-OSS models."""
        params = deepseek_provider.translate_reasoning_level("off")
        assert params == {"think": False}

    def test_deepseek_translate_high_to_true(
        self, deepseek_provider: api.LLMProvider
    ) -> None:
        """high level should map to think: true for non-GPT-OSS models."""
        params = deepseek_provider.translate_reasoning_level("high")
        assert params == {"think": True}

    def test_non_reasoning_model_returns_empty(
        self, non_reasoning_provider: api.LLMProvider
    ) -> None:
        """Non-reasoning models should return empty dict."""
        params = non_reasoning_provider.translate_reasoning_level("high")
        assert params == {}


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
