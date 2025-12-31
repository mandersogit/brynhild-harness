"""
Shared pytest fixtures for Brynhild tests.

This file is automatically loaded by pytest. Fixtures defined here are
available to all test files without explicit imports.
"""

import importlib as _importlib
import os as _os
import pathlib as _pathlib
import site as _site
import sys as _sys
import typing as _typing
import unittest.mock as _mock

import click.testing as _click_testing
import pytest as _pytest

import brynhild.api.base as api_base
import brynhild.api.types as api_types
import brynhild.config as config
import brynhild.session as session
import brynhild.tools.base as tools_base
import brynhild.tools.registry as tools_registry

# =============================================================================
# Pytest Hooks
# =============================================================================


def pytest_configure(config: _pytest.Config) -> None:  # noqa: F811 - shadows import but pytest requires this name
    """Configure test session."""
    # Skip legacy env var migration check during tests
    # This allows tests to run even if the user's .env has legacy vars
    _os.environ["BRYNHILD_SKIP_MIGRATION_CHECK"] = "1"

    # Check if we're running ollama_local tests
    markexpr = config.getoption("-m", default="")
    if "ollama_local" in str(markexpr):
        # Show effective host (BRYNHILD_OLLAMA_HOST takes precedence over OLLAMA_HOST)
        brynhild_host = _os.environ.get("BRYNHILD_OLLAMA_HOST", "")
        ollama_host = _os.environ.get("OLLAMA_HOST", "")
        effective_host = brynhild_host or ollama_host or "localhost"
        ollama_model = _os.environ.get("BRYNHILD_OLLAMA_MODEL", "(not set)")
        print("\n" + "=" * 60)
        print("Ollama Test Configuration:")
        print(f"  Host (effective)      = {effective_host}")
        if brynhild_host:
            print("    (from BRYNHILD_OLLAMA_HOST)")
        elif ollama_host:
            print("    (from OLLAMA_HOST)")
        else:
            print("    (default)")
        print(f"  BRYNHILD_OLLAMA_MODEL = {ollama_model}")
        print("=" * 60)

# Environment keys that should be cleared for isolated tests
ENV_KEYS_TO_CLEAR = [
    "OPENROUTER_API_KEY",
    "BRYNHILD_PROVIDER",
    "BRYNHILD_MODEL",
    "BRYNHILD_VERBOSE",
    "BRYNHILD_MAX_TOKENS",
    "BRYNHILD_OUTPUT_FORMAT",
    "BRYNHILD_TEST_MODEL",
]

# =============================================================================
# Live Test Model Configuration
# =============================================================================

# Default model for all live tests
LIVE_TEST_MODEL = "openai/gpt-oss-120b"

# Model tiers for parameterized tests
LIVE_TEST_MODELS_CHEAP = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "x-ai/grok-4.1-fast:free",
]

LIVE_TEST_MODELS_DIVERSE = [
    "openai/gpt-oss-120b",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",
    "nousresearch/hermes-4-70b",
    "qwen/qwen3-next-80b-a3b-thinking",
]

LIVE_TEST_MODELS_LARGE_CONTEXT = [
    "x-ai/grok-4.1-fast:free",
]


@_pytest.fixture
def clean_env() -> dict[str, str]:
    """
    Return environment dict with test-related keys removed.

    Use with mock.patch.dict to isolate tests from the actual environment.
    """
    return {k: v for k, v in _os.environ.items() if k not in ENV_KEYS_TO_CLEAR}


@_pytest.fixture
def isolated_env(clean_env: dict[str, str]):
    """
    Context manager that isolates tests from environment variables.

    Usage:
        def test_something(isolated_env):
            with isolated_env:
                settings = config.Settings.construct_without_dotenv()
    """
    return _mock.patch.dict(_os.environ, clean_env, clear=True)


@_pytest.fixture
def clean_settings(isolated_env) -> config.Settings:
    """
    Settings instance isolated from environment and .env file.

    This fixture ensures tests get predictable default settings.
    """
    with isolated_env:
        return config.Settings.construct_without_dotenv()


@_pytest.fixture
def session_manager(tmp_path: _pathlib.Path) -> session.SessionManager:
    """
    SessionManager with a temporary directory for test isolation.

    Sessions created with this manager are automatically cleaned up.
    """
    sessions_dir = tmp_path / "sessions"
    return session.SessionManager(sessions_dir)


@_pytest.fixture
def sample_session() -> session.Session:
    """
    A sample session with some messages for testing.
    """
    sess = session.Session.create(
        model="test-model",
        provider="test-provider",
    )
    sess.add_message("user", "Hello, how are you?")
    sess.add_message("assistant", "I'm doing well, thank you!")
    sess.title = "Test Conversation"
    return sess


@_pytest.fixture
def mock_api_key():
    """
    Fixture that provides a mock API key in the environment.

    Usage:
        def test_with_api_key(mock_api_key):
            # OPENROUTER_API_KEY is now set to "test-api-key"
            settings = config.Settings.construct_without_dotenv()
            assert settings.get_api_key() == "test-api-key"
    """
    with _mock.patch.dict(
        _os.environ,
        {"OPENROUTER_API_KEY": "test-api-key", "BRYNHILD_PROVIDER": "openrouter"},
    ):
        yield "test-api-key"


# =============================================================================
# Integration/System Test Fixtures
# =============================================================================


@_pytest.fixture
def live_model() -> str:
    """Default model for live tests."""
    return _os.environ.get("BRYNHILD_TEST_MODEL", LIVE_TEST_MODEL)


@_pytest.fixture
def isolated_workspace(tmp_path: _pathlib.Path) -> _pathlib.Path:
    """Create an isolated project workspace with standard structure."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Create minimal project structure
    (workspace / "pyproject.toml").write_text(
        '[project]\nname = "test-project"\nversion = "0.1.0"\n'
    )
    (workspace / "src").mkdir()
    (workspace / "tests").mkdir()

    return workspace


@_pytest.fixture
def project_with_hooks(isolated_workspace: _pathlib.Path) -> _pathlib.Path:
    """Workspace with .brynhild/hooks.yaml configured."""
    brynhild_dir = isolated_workspace / ".brynhild"
    brynhild_dir.mkdir()

    hooks_yaml = brynhild_dir / "hooks.yaml"
    hooks_yaml.write_text(
        """version: 1
hooks:
  pre_tool_use:
    - name: log_tools
      type: command
      command: "echo $BRYNHILD_TOOL_NAME"
"""
    )

    return isolated_workspace


# =============================================================================
# Mock Provider for Integration Tests
# =============================================================================


class MockProvider(api_base.LLMProvider):
    """Mock LLM provider for integration/system tests."""

    def __init__(
        self,
        responses: list[api_types.CompletionResponse] | None = None,
        stream_events: list[list[api_types.StreamEvent]] | None = None,
        should_fail: bool = False,
        fail_message: str = "Mock failure",
    ) -> None:
        self._responses = responses or []
        self._stream_events = stream_events or []
        self._response_index = 0
        self._stream_index = 0
        self._should_fail = should_fail
        self._fail_message = fail_message

    @property
    def name(self) -> str:
        return "mock"

    @property
    def model(self) -> str:
        return "mock-model"

    def supports_tools(self) -> bool:
        return True

    def supports_reasoning(self) -> bool:
        return False

    async def complete(
        self,
        messages: list[dict[str, _typing.Any]],  # noqa: ARG002
        *,
        system: str | None = None,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
        tools: list[api_types.Tool] | None = None,  # noqa: ARG002
    ) -> api_types.CompletionResponse:
        if self._should_fail:
            raise RuntimeError(self._fail_message)
        if self._response_index < len(self._responses):
            response = self._responses[self._response_index]
            self._response_index += 1
            return response
        return api_types.CompletionResponse(
            id="mock-id",
            content="mock response",
            stop_reason="stop",
            usage=api_types.Usage(input_tokens=10, output_tokens=5),
        )

    async def stream(
        self,
        messages: list[dict[str, _typing.Any]],  # noqa: ARG002
        *,
        system: str | None = None,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
        tools: list[api_types.Tool] | None = None,  # noqa: ARG002
    ) -> _typing.AsyncIterator[api_types.StreamEvent]:
        if self._should_fail:
            raise RuntimeError(self._fail_message)
        if self._stream_index < len(self._stream_events):
            events = self._stream_events[self._stream_index]
            self._stream_index += 1
            for event in events:
                yield event
        else:
            yield api_types.StreamEvent(type="text_delta", text="mock response")
            yield api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            )


class ScriptedMockProvider(api_base.LLMProvider):
    """
    Mock provider that follows a script of responses.

    Useful for testing multi-turn conversations and tool loops.
    """

    def __init__(
        self,
        script: list[dict[str, _typing.Any]],
        name: str = "mock",
        model: str = "mock-model",
    ) -> None:
        """
        Initialize with a script of responses.

        Script format:
        [
            {
                "text": "I'll help you",
                "tool_calls": [{"name": "Bash", "input": {"command": "ls"}}],
            },
            {
                "text": "Here are the files: ...",
            },
        ]
        """
        self._script = script
        self._script_index = 0
        self._name = name
        self._model = model

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return self._model

    def supports_tools(self) -> bool:
        return True

    def supports_reasoning(self) -> bool:
        return False

    async def complete(
        self,
        messages: list[dict[str, _typing.Any]],  # noqa: ARG002
        *,
        system: str | None = None,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
        tools: list[api_types.Tool] | None = None,  # noqa: ARG002
    ) -> api_types.CompletionResponse:
        # Use stream internally and collect
        text_parts = []
        tool_uses = []
        async for event in self.stream(messages, system=system, max_tokens=max_tokens, tools=tools):
            if event.type == "text_delta" and event.text:
                text_parts.append(event.text)
            elif event.type == "tool_use_start" and event.tool_use:
                tool_uses.append(event.tool_use)

        return api_types.CompletionResponse(
            id="mock-id",
            content="".join(text_parts),
            stop_reason="tool_use" if tool_uses else "stop",
            usage=api_types.Usage(input_tokens=100, output_tokens=50),
            tool_uses=tool_uses if tool_uses else None,
        )

    async def stream(
        self,
        messages: list[dict[str, _typing.Any]],  # noqa: ARG002
        *,
        system: str | None = None,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
        tools: list[api_types.Tool] | None = None,  # noqa: ARG002
    ) -> _typing.AsyncIterator[api_types.StreamEvent]:
        """Stream the next scripted response."""
        if self._script_index >= len(self._script):
            # Default response when script exhausted
            yield api_types.StreamEvent(type="text_delta", text="[Script exhausted]")
            yield api_types.StreamEvent(
                type="message_stop",
                stop_reason="stop",
                usage=api_types.Usage(input_tokens=10, output_tokens=5),
            )
            return

        response = self._script[self._script_index]
        self._script_index += 1

        # Yield events based on script
        if "thinking" in response:
            yield api_types.StreamEvent(
                type="thinking_delta",
                thinking=response["thinking"],
            )

        if "text" in response:
            yield api_types.StreamEvent(
                type="text_delta",
                text=response["text"],
            )

        if "tool_calls" in response:
            for tc in response["tool_calls"]:
                yield api_types.StreamEvent(
                    type="tool_use_start",
                    tool_use=api_types.ToolUse(
                        id=tc.get("id", f"tool-{self._script_index}"),
                        name=tc["name"],
                        input=tc.get("input", {}),
                    ),
                )

        stop_reason = "tool_use" if response.get("tool_calls") else "stop"
        yield api_types.StreamEvent(
            type="message_stop",
            stop_reason=stop_reason,
            usage=api_types.Usage(
                input_tokens=response.get("input_tokens", 100),
                output_tokens=response.get("output_tokens", 50),
            ),
        )


@_pytest.fixture
def mock_provider() -> MockProvider:
    """Create a basic mock provider."""
    return MockProvider()


@_pytest.fixture
def mock_provider_factory() -> _typing.Callable[..., MockProvider]:
    """Factory for creating mock providers with specific behaviors."""

    def _create(
        responses: list[api_types.CompletionResponse] | None = None,
        stream_events: list[list[api_types.StreamEvent]] | None = None,
        should_fail: bool = False,
        fail_message: str = "Mock failure",
    ) -> MockProvider:
        return MockProvider(
            responses=responses,
            stream_events=stream_events,
            should_fail=should_fail,
            fail_message=fail_message,
        )

    return _create


@_pytest.fixture
def scripted_provider_factory() -> _typing.Callable[..., ScriptedMockProvider]:
    """Factory for creating scripted mock providers."""

    def _create(
        script: list[dict[str, _typing.Any]],
        name: str = "mock",
        model: str = "mock-model",
    ) -> ScriptedMockProvider:
        return ScriptedMockProvider(script=script, name=name, model=model)

    return _create


# =============================================================================
# Mock Tool for Integration Tests
# =============================================================================


class MockTool(tools_base.Tool):
    """A configurable mock tool for integration tests."""

    def __init__(
        self,
        name: str = "MockTool",
        requires_permission: bool = False,
        success: bool = True,
        output: str = "mock output",
        error: str | None = None,
    ) -> None:
        self._name = name
        self._requires_permission = requires_permission
        self._success = success
        self._output = output
        self._error = error
        self.call_count = 0
        self.last_input: dict[str, _typing.Any] | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Mock tool: {self._name}"

    @property
    def requires_permission(self) -> bool:
        return self._requires_permission

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Input value"},
            },
        }

    async def execute(self, input: dict[str, _typing.Any]) -> tools_base.ToolResult:
        self.call_count += 1
        self.last_input = input
        return tools_base.ToolResult(
            success=self._success,
            output=self._output,
            error=self._error,
        )


class FailingTool(tools_base.Tool):
    """A tool that always fails - useful for testing error handling."""

    def __init__(
        self,
        name: str = "FailingTool",
        error_message: str = "Tool execution failed",
    ) -> None:
        self._name = name
        self._error_message = error_message
        self.call_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "A tool that always fails"

    @property
    def requires_permission(self) -> bool:
        return False

    @property
    def input_schema(self) -> dict[str, _typing.Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, input: dict[str, _typing.Any]) -> tools_base.ToolResult:  # noqa: ARG002
        self.call_count += 1
        return tools_base.ToolResult(
            success=False,
            output="",
            error=self._error_message,
        )


@_pytest.fixture
def mock_tool() -> MockTool:
    """Create a basic mock tool."""
    return MockTool()


@_pytest.fixture
def mock_tool_registry() -> tools_registry.ToolRegistry:
    """Create a registry with a mock tool."""
    registry = tools_registry.ToolRegistry()
    registry.register(MockTool())
    return registry


# =============================================================================
# CLI Test Fixtures
# =============================================================================


@_pytest.fixture
def cli_runner() -> _click_testing.CliRunner:
    """CLI runner for end-to-end tests."""
    return _click_testing.CliRunner()


# =============================================================================
# Realistic Token Tracking Fixtures
# =============================================================================


class RealisticUsageMockProvider(api_base.LLMProvider):
    """
    Mock provider that returns realistic GROWING context sizes.

    This reveals accumulation bugs that constant-value mocks hide.

    LLM providers return ABSOLUTE context size per call:
    - Call 1: 1000 tokens (system + user message)
    - Call 2: 2500 tokens (+ assistant + tool result)
    - Call 3: 4000 tokens (+ more messages)

    NOT incremental deltas.
    """

    def __init__(
        self,
        usage_sequence: list[tuple[int, int]],
        tool_calls_on: list[int] | None = None,
    ) -> None:
        """
        Initialize with a sequence of (input_tokens, output_tokens) per call.

        Args:
            usage_sequence: List of (input_tokens, output_tokens) tuples.
                           input_tokens should be GROWING (realistic context).
            tool_calls_on: List of call indices (0-based) that should return tool calls.
        """
        self._usage_sequence = usage_sequence
        self._tool_calls_on = set(tool_calls_on or [])
        self._call_index = 0

    @property
    def name(self) -> str:
        return "realistic-mock"

    @property
    def model(self) -> str:
        return "realistic-mock-model"

    def supports_tools(self) -> bool:
        return True

    def supports_reasoning(self) -> bool:
        return False

    async def complete(
        self,
        messages: list[dict[str, _typing.Any]],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        tools: list[api_types.Tool] | None = None,
    ) -> api_types.CompletionResponse:
        text_parts = []
        tool_uses = []
        usage = None

        async for event in self.stream(
            messages, system=system, max_tokens=max_tokens, tools=tools
        ):
            if event.type == "text_delta" and event.text:
                text_parts.append(event.text)
            elif event.type == "tool_use_start" and event.tool_use:
                tool_uses.append(event.tool_use)
            elif event.type == "message_delta" and event.usage:
                usage = event.usage

        return api_types.CompletionResponse(
            id=f"call-{self._call_index}",
            content="".join(text_parts),
            stop_reason="tool_use" if tool_uses else "stop",
            usage=usage or api_types.Usage(input_tokens=0, output_tokens=0),
            tool_uses=tool_uses if tool_uses else None,
        )

    async def stream(
        self,
        messages: list[dict[str, _typing.Any]],  # noqa: ARG002
        *,
        system: str | None = None,  # noqa: ARG002
        max_tokens: int = 4096,  # noqa: ARG002
        tools: list[api_types.Tool] | None = None,  # noqa: ARG002
    ) -> _typing.AsyncIterator[api_types.StreamEvent]:
        current_call = self._call_index

        if current_call < len(self._usage_sequence):
            input_tokens, output_tokens = self._usage_sequence[current_call]
        else:
            input_tokens, output_tokens = 1000, 50

        if current_call in self._tool_calls_on:
            yield api_types.StreamEvent(type="text_delta", text="Using tool...")
            yield api_types.StreamEvent(
                type="tool_use_start",
                tool_use=api_types.ToolUse(
                    id=f"tool-{current_call}",
                    name="MockTool",
                    input={"value": f"call-{current_call}"},
                ),
            )
            stop_reason = "tool_use"
        else:
            yield api_types.StreamEvent(
                type="text_delta", text=f"Response for call {current_call}"
            )
            stop_reason = "stop"

        yield api_types.StreamEvent(
            type="message_delta",
            stop_reason=stop_reason,
            usage=api_types.Usage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            ),
        )

        self._call_index += 1


@_pytest.fixture
def realistic_usage_provider_factory() -> _typing.Callable[..., RealisticUsageMockProvider]:
    """
    Factory for creating mock providers with realistic token tracking.

    Usage:
        def test_something(realistic_usage_provider_factory):
            provider = realistic_usage_provider_factory(
                usage_sequence=[(1000, 50), (2500, 100), (4000, 150)],
                tool_calls_on=[0, 1],  # First two calls return tool uses
            )
    """

    def _create(
        usage_sequence: list[tuple[int, int]],
        tool_calls_on: list[int] | None = None,
    ) -> RealisticUsageMockProvider:
        return RealisticUsageMockProvider(
            usage_sequence=usage_sequence,
            tool_calls_on=tool_calls_on,
        )

    return _create


# =============================================================================
# Test Utilities
# =============================================================================


def create_stream_events_for_response(
    text: str,
    tool_calls: list[dict[str, _typing.Any]] | None = None,
    thinking: str | None = None,
) -> list[api_types.StreamEvent]:
    """Create a list of stream events that produce a given response."""
    events: list[api_types.StreamEvent] = []

    if thinking:
        events.append(
            api_types.StreamEvent(
                type="thinking_delta",
                thinking=thinking,
            )
        )

    if text:
        # Chunk text into pieces for realistic streaming
        chunk_size = 10
        for i in range(0, len(text), chunk_size):
            events.append(
                api_types.StreamEvent(
                    type="text_delta",
                    text=text[i : i + chunk_size],
                )
            )

    if tool_calls:
        for tc in tool_calls:
            events.append(
                api_types.StreamEvent(
                    type="tool_use_start",
                    tool_use=api_types.ToolUse(
                        id=tc.get("id", "test-id"),
                        name=tc["name"],
                        input=tc.get("input", {}),
                    ),
                )
            )

    stop_reason = "tool_use" if tool_calls else "stop"
    events.append(
        api_types.StreamEvent(
            type="message_stop",
            stop_reason=stop_reason,
            usage=api_types.Usage(input_tokens=100, output_tokens=50),
        )
    )

    return events


# =============================================================================
# Entry Point Plugin Fixture
# =============================================================================

# Permanent fixture directory containing the test plugin with dist-info
_TEST_PLUGIN_SITE_PACKAGES = _pathlib.Path(__file__).parent / "fixtures" / "site-packages"


@_pytest.fixture
def installed_test_plugin() -> _typing.Generator[_pathlib.Path, None, None]:
    """
    Fixture that makes the test plugin discoverable via entry points.

    Uses a permanent fixture directory (tests/fixtures/site-packages/) that
    contains a pre-built package with .dist-info. The fixture simply adds
    this directory as a site-packages location and invalidates caches.

    This approach:
    - Uses site.addsitedir() for proper site-packages semantics
    - Doesn't copy files - uses permanent fixtures
    - Is fast and doesn't pollute temp directories

    Usage:
        def test_entry_points(installed_test_plugin):
            import importlib.metadata as meta
            eps = meta.entry_points(group='brynhild.plugins')
            assert 'test-plugin' in [ep.name for ep in eps]

    Yields:
        Path to the fixture site-packages directory.
    """
    site_packages = _TEST_PLUGIN_SITE_PACKAGES
    site_packages_str = str(site_packages)

    # Add as a site-packages directory (processes .pth files if any exist)
    _site.addsitedir(site_packages_str)

    # Invalidate import caches so importlib.metadata rediscovers distributions
    _importlib.invalidate_caches()

    # Remove any cached modules from previous test runs
    for mod_name in list(_sys.modules.keys()):
        if mod_name.startswith("brynhild_test_plugin"):
            del _sys.modules[mod_name]

    try:
        yield site_packages
    finally:
        # Cleanup: remove from sys.path
        # site.addsitedir adds to sys.path, so we remove from there
        if site_packages_str in _sys.path:
            _sys.path.remove(site_packages_str)

        # Invalidate caches again so subsequent tests don't see the plugin
        _importlib.invalidate_caches()

        # Remove cached modules
        for mod_name in list(_sys.modules.keys()):
            if mod_name.startswith("brynhild_test_plugin"):
                del _sys.modules[mod_name]
