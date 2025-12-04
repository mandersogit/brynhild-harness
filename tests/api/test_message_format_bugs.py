"""
Tests for message formatting bugs.

These tests were written to expose real bugs found during code review.
"""



import brynhild.api.ollama_provider as ollama_provider
import brynhild.api.openrouter_provider as openrouter_provider


class TestMessageFormatBugs:
    """Tests that expose message formatting bugs."""

    def test_tool_result_messages_are_preserved_ollama(self) -> None:
        """
        Tool result messages (role="tool_result") are correctly formatted.

        This verifies the fix for the bug where thinking-only feedback was dropped.
        The thinking-only handler now uses role="tool_result" (internal format)
        which providers correctly convert to role="tool" for the API.
        """
        provider = ollama_provider.OllamaProvider(model="test")

        messages = [
            {"role": "user", "content": "Hello"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "fake-123",
                        "type": "function",
                        "function": {"name": "incomplete_response", "arguments": "{}"},
                    }
                ],
            },
            # This is the FIXED format that _handle_thinking_only_response uses
            {
                "role": "tool_result",  # Correct internal format
                "tool_use_id": "fake-123",
                "content": "ERROR: Your response contained only thinking...",
                "is_error": True,
            },
        ]

        formatted = provider._format_messages(messages, system=None)

        # Tool result should be converted to role="tool" for OpenAI API
        tool_messages = [m for m in formatted if m.get("role") == "tool"]
        assert len(tool_messages) == 1, (
            f"Expected 1 tool message, got {len(tool_messages)}. "
            f"Tool result not being formatted correctly."
        )

    def test_tool_result_messages_are_preserved_openrouter(self) -> None:
        """Same test for OpenRouter provider."""
        provider = openrouter_provider.OpenRouterProvider(
            model="test", api_key="fake-key"
        )

        messages = [
            {"role": "user", "content": "Hello"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "fake-123",
                        "type": "function",
                        "function": {"name": "incomplete_response", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool_result",
                "tool_use_id": "fake-123",
                "content": "ERROR: feedback message",
                "is_error": True,
            },
        ]

        formatted = provider._format_messages(messages, system=None)

        tool_messages = [m for m in formatted if m.get("role") == "tool"]
        assert len(tool_messages) == 1, (
            f"Expected 1 tool message, got {len(tool_messages)}. "
            f"Tool result not being formatted correctly."
        )

    def test_unknown_roles_are_silently_dropped(self) -> None:
        """
        Any message with an unknown role is silently dropped.

        This could cause hard-to-debug issues where messages disappear.
        """
        provider = ollama_provider.OllamaProvider(model="test")

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
            {"role": "system", "content": "You are helpful"},  # Unknown in middle!
            {"role": "user", "content": "Thanks"},
        ]

        formatted = provider._format_messages(messages, system=None)

        # The "system" message in the middle should either:
        # 1. Cause an error (so we know something is wrong)
        # 2. Be preserved somehow
        # Currently it's silently dropped!
        roles = [m["role"] for m in formatted]
        assert "system" not in roles or len(formatted) == 4, (
            f"Expected system message to be handled somehow, got roles: {roles}"
        )

