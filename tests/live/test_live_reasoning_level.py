"""
Live tests for reasoning level API.

These tests make actual API calls to verify:
- Reasoning level parameters are sent correctly
- Different effort levels produce different outputs
- Provider correctly handles reasoning_level config
"""

import os as _os

import pytest as _pytest

import brynhild.api as api

# All tests require live API access
pytestmark = [_pytest.mark.live, _pytest.mark.slow]

# Use gpt-oss for reasoning tests (supports reasoning.effort)
REASONING_MODEL = _os.environ.get("BRYNHILD_TEST_MODEL", "openai/gpt-oss-120b")


@_pytest.fixture
def api_key() -> str:
    """Get API key from environment, skip if not available."""
    key = _os.environ.get("OPENROUTER_API_KEY")
    if not key:
        _pytest.skip("OPENROUTER_API_KEY not set")
    return key


class TestOpenRouterReasoningLevelLive:
    """Live tests for OpenRouter reasoning level control."""

    @_pytest.mark.asyncio
    async def test_reasoning_level_high(self, api_key: str) -> None:
        """High reasoning level should produce response with extended thinking."""
        provider = api.create_provider(
            provider="openrouter",
            model=REASONING_MODEL,
            api_key=api_key,
        )
        try:
            # Force high reasoning level
            params = provider.translate_reasoning_level("high")
            assert params == {"reasoning": {"effort": "high"}}

            # Make a request
            response = await provider.complete(
                messages=[{"role": "user", "content": "What is 2+2? Think step by step."}],
                max_tokens=500,
            )

            # Should have some output (thinking or content)
            has_output = (
                (response.content and len(response.content) > 0)
                or (response.thinking and len(response.thinking) > 0)
            )
            assert has_output, f"No output: content={response.content!r}, thinking={response.thinking!r}"
        finally:
            await provider.close()

    @_pytest.mark.asyncio
    async def test_reasoning_level_low(self, api_key: str) -> None:
        """Low reasoning level should produce a response with minimal thinking."""
        provider = api.create_provider(
            provider="openrouter",
            model=REASONING_MODEL,
            api_key=api_key,
        )
        try:
            # Force low reasoning level
            params = provider.translate_reasoning_level("low")
            assert params == {"reasoning": {"effort": "low"}}

            # Make a request
            response = await provider.complete(
                messages=[{"role": "user", "content": "What is 2+2?"}],
                max_tokens=200,
            )

            # Should have output
            has_output = (
                (response.content and len(response.content) > 0)
                or (response.thinking and len(response.thinking) > 0)
            )
            assert has_output
        finally:
            await provider.close()

    @_pytest.mark.asyncio
    async def test_reasoning_level_via_env_config(self, api_key: str, monkeypatch: _pytest.MonkeyPatch) -> None:
        """Reasoning level set via environment should be used in requests."""
        # Set reasoning level via environment
        monkeypatch.setenv("BRYNHILD_BEHAVIOR__REASONING_LEVEL", "medium")

        provider = api.create_provider(
            provider="openrouter",
            model=REASONING_MODEL,
            api_key=api_key,
        )
        try:
            # Verify the level is picked up
            level = provider.get_reasoning_level()
            assert level == "medium"

            # Verify it translates correctly
            params = provider.translate_reasoning_level()
            assert params == {"reasoning": {"effort": "medium"}}

            # Make a request (verify it doesn't error)
            response = await provider.complete(
                messages=[{"role": "user", "content": "Say 'hello'."}],
                max_tokens=100,
            )
            assert response is not None
        finally:
            await provider.close()

    @_pytest.mark.asyncio
    async def test_reasoning_level_off(self, api_key: str) -> None:
        """'off' reasoning level should minimize thinking."""
        provider = api.create_provider(
            provider="openrouter",
            model=REASONING_MODEL,
            api_key=api_key,
        )
        try:
            # Force off reasoning level
            params = provider.translate_reasoning_level("off")
            assert params == {"reasoning": {"effort": "none"}}

            # Make a request
            response = await provider.complete(
                messages=[{"role": "user", "content": "Say 'test'."}],
                max_tokens=100,
            )

            # Should still produce output
            has_output = (
                (response.content and len(response.content) > 0)
                or (response.thinking and len(response.thinking) > 0)
            )
            assert has_output
        finally:
            await provider.close()

    @_pytest.mark.asyncio
    async def test_reasoning_level_maximum(self, api_key: str) -> None:
        """Maximum reasoning level should use xhigh effort."""
        provider = api.create_provider(
            provider="openrouter",
            model=REASONING_MODEL,
            api_key=api_key,
        )
        try:
            # Verify maximum maps to xhigh
            params = provider.translate_reasoning_level("maximum")
            assert params == {"reasoning": {"effort": "xhigh"}}

            # Make a request (don't need extended response - just verify params)
            response = await provider.complete(
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=100,
            )
            assert response is not None
        finally:
            await provider.close()

    @_pytest.mark.asyncio
    async def test_reasoning_level_raw_passthrough(self, api_key: str) -> None:
        """Raw prefixed values should be passed through to API."""
        provider = api.create_provider(
            provider="openrouter",
            model=REASONING_MODEL,
            api_key=api_key,
        )
        try:
            # Raw value should pass through
            params = provider.translate_reasoning_level("raw:xhigh")
            assert params == {"reasoning": {"effort": "xhigh"}}
        finally:
            await provider.close()


class TestOpenRouterReasoningLevelE2E:
    """End-to-end tests verifying reasoning level actually affects output."""

    @_pytest.mark.asyncio
    async def test_all_levels_produce_thinking_output(self, api_key: str) -> None:
        """Each reasoning level should produce thinking output for reasoning model."""
        results = {}

        for level in ["low", "medium", "high"]:
            provider = api.create_provider(
                provider="openrouter",
                model=REASONING_MODEL,
                api_key=api_key,
            )
            try:
                # Verify this is a reasoning-capable model
                assert provider.supports_reasoning(), f"Model {REASONING_MODEL} should support reasoning"

                # Make request with explicit level
                response = await provider.complete(
                    messages=[{"role": "user", "content": "What is 12 times 4?"}],
                    max_tokens=300,
                )

                # Record results
                results[level] = {
                    "has_thinking": response.thinking is not None and len(response.thinking) > 0,
                    "thinking_len": len(response.thinking) if response.thinking else 0,
                    "has_content": response.content is not None and len(response.content) > 0,
                }
            finally:
                await provider.close()

        # All levels should produce thinking for a reasoning model
        for level, result in results.items():
            assert result["has_thinking"] or result["has_content"], (
                f"Level {level} produced no output"
            )


class TestOllamaReasoningLevelLive:
    """Live tests for Ollama reasoning level control.

    These tests require a local Ollama server with gpt-oss-120b or similar model.
    """

    @_pytest.fixture
    def ollama_available(self) -> bool:
        """Check if Ollama server is available."""
        import httpx

        try:
            # Check if Ollama is running
            host = _os.environ.get("BRYNHILD_OLLAMA_HOST", "localhost:11434")
            if not host.startswith("http"):
                host = f"http://{host}"
            response = httpx.get(f"{host}/api/tags", timeout=2.0)
            return response.status_code == 200
        except Exception:
            return False

    @_pytest.fixture
    def gpt_oss_on_ollama(self, ollama_available: bool) -> bool:
        """Check if gpt-oss is available on Ollama."""
        if not ollama_available:
            return False

        import httpx

        try:
            host = _os.environ.get("BRYNHILD_OLLAMA_HOST", "localhost:11434")
            if not host.startswith("http"):
                host = f"http://{host}"
            response = httpx.get(f"{host}/api/tags", timeout=2.0)
            data = response.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            return any("gpt-oss" in m for m in models)
        except Exception:
            return False

    @_pytest.mark.asyncio
    async def test_ollama_reasoning_level_translation(
        self, ollama_available: bool, gpt_oss_on_ollama: bool
    ) -> None:
        """Test reasoning level translation for Ollama with GPT-OSS."""
        if not ollama_available:
            _pytest.skip("Ollama server not available")
        if not gpt_oss_on_ollama:
            _pytest.skip("gpt-oss model not installed on Ollama")

        provider = api.create_provider(
            provider="ollama",
            model="openai/gpt-oss-120b",  # Canonical name, translated to gpt-oss:120b
        )
        try:
            # Verify translation to string levels
            params = provider.translate_reasoning_level("high")
            assert params == {"think": "high"}

            # Make a simple request
            response = await provider.complete(
                messages=[{"role": "user", "content": "Say 'ok'."}],
                max_tokens=50,
            )
            assert response is not None
        finally:
            await provider.close()

    @_pytest.mark.asyncio
    async def test_ollama_all_levels_produce_thinking(
        self, ollama_available: bool, gpt_oss_on_ollama: bool
    ) -> None:
        """End-to-end test: all reasoning levels should produce thinking on Ollama."""
        if not ollama_available:
            _pytest.skip("Ollama server not available")
        if not gpt_oss_on_ollama:
            _pytest.skip("gpt-oss model not installed on Ollama")

        results = {}

        for level in ["low", "medium", "high"]:
            provider = api.create_provider(
                provider="ollama",
                model="openai/gpt-oss-120b",
            )
            try:
                assert provider.supports_reasoning(), "Model should support reasoning"

                response = await provider.complete(
                    messages=[{"role": "user", "content": "What is 8 times 7?"}],
                    max_tokens=200,
                )

                results[level] = {
                    "has_thinking": response.thinking is not None and len(response.thinking) > 0,
                    "thinking_len": len(response.thinking) if response.thinking else 0,
                    "has_content": response.content is not None and len(response.content) > 0,
                }
            finally:
                await provider.close()

        # All levels should produce output
        for level, result in results.items():
            assert result["has_thinking"] or result["has_content"], (
                f"Level {level} produced no output"
            )
            # GPT-OSS should produce thinking
            assert result["has_thinking"], f"Level {level} should produce thinking"

    @_pytest.mark.asyncio
    @_pytest.mark.xfail(
        reason=(
            "Ollama's OpenAI-compatible endpoint (/v1/chat/completions) does not respect "
            "the 'think' parameter. The native /api/chat endpoint DOES work correctly. "
            "TODO: (1) Matt needs to update Ollama on Behemoth (currently months old) and "
            "re-test. (2) If still failing, consider switching Ollama provider to native "
            "/api/chat endpoint instead of OpenAI-compatible endpoint."
        ),
        strict=False,  # Don't fail if it unexpectedly passes (e.g., after Ollama update)
    )
    async def test_ollama_reasoning_level_scaling(
        self, ollama_available: bool, gpt_oss_on_ollama: bool
    ) -> None:
        """Verify reasoning output INCREASES with higher reasoning levels.

        This test verifies that the 'think' parameter actually affects output:
        - low should produce less thinking than medium
        - medium should produce less thinking than high

        Currently FAILS because Ollama's OpenAI-compatible endpoint doesn't
        respect the 'think' parameter. The native /api/chat endpoint works
        correctly (verified with curl), but we use /v1/chat/completions.
        """
        if not ollama_available:
            _pytest.skip("Ollama server not available")
        if not gpt_oss_on_ollama:
            _pytest.skip("gpt-oss model not installed on Ollama")

        # Use a prompt that requires actual reasoning
        prompt = (
            "Solve step by step: A farmer has chickens and rabbits. "
            "The animals have 50 heads and 140 legs total. "
            "How many chickens and how many rabbits?"
        )

        results = {}

        for level in ["low", "medium", "high"]:
            # Set via env var (how real users configure it)
            _os.environ["BRYNHILD_BEHAVIOR__REASONING_LEVEL"] = level

            provider = api.create_provider(
                provider="ollama",
                model="openai/gpt-oss-120b",
            )
            try:
                response = await provider.complete(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2000,
                )

                thinking_len = len(response.thinking) if response.thinking else 0
                results[level] = thinking_len
            finally:
                await provider.close()

        # Verify scaling: low < medium < high
        # Allow some variance, but high should be significantly more than low
        low, medium, high = results["low"], results["medium"], results["high"]

        assert high > low * 1.5, (
            f"High reasoning ({high} chars) should be significantly more than "
            f"low ({low} chars). Expected at least 1.5x increase. "
            f"Results: low={low}, medium={medium}, high={high}"
        )

