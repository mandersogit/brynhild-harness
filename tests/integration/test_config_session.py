"""Integration tests for Config + Session + Storage interaction."""

import os as _os
import pathlib as _pathlib
import unittest.mock as _mock

import pytest as _pytest

import brynhild.config as config
import brynhild.session as session


@_pytest.mark.integration
class TestConfigSessionIntegration:
    """Tests for Config and Session integration."""

    def test_session_uses_configured_model(self) -> None:
        """Session stores the model from configuration."""
        # Setup: Create session with specific model
        sess = session.Session.create(
            model="test-model-123",
            provider="test-provider",
        )

        # Verify: Session stores the model
        assert sess.model == "test-model-123"
        assert sess.provider == "test-provider"

    def test_session_save_load_preserves_messages(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Session save and load preserves all messages."""
        # Setup: Create session manager and session with messages
        sessions_dir = tmp_path / "sessions"
        manager = session.SessionManager(sessions_dir)

        sess = session.Session.create(
            model="test-model",
            provider="openrouter",  # Must be valid provider
        )
        sess.add_message("user", "Hello!")
        sess.add_message("assistant", "Hi there!")
        sess.add_message("user", "How are you?")
        sess.title = "Test Conversation"

        # Save session
        manager.save(sess)

        # Load session
        loaded = manager.load(sess.id)

        # Verify: All data preserved
        assert loaded is not None
        assert loaded.id == sess.id
        assert loaded.model == "test-model"
        assert loaded.provider == "openrouter"
        assert loaded.title == "Test Conversation"
        assert len(loaded.messages) == 3
        # Messages are Message objects, not dicts
        assert loaded.messages[0].role == "user"
        assert loaded.messages[0].content == "Hello!"
        assert loaded.messages[1].role == "assistant"
        assert loaded.messages[1].content == "Hi there!"
        assert loaded.messages[2].role == "user"
        assert loaded.messages[2].content == "How are you?"

    def test_session_manager_respects_config_dir(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """SessionManager uses the configured directory."""
        # Setup: Create manager with specific directory
        custom_dir = tmp_path / "custom_sessions"
        manager = session.SessionManager(custom_dir)

        # Create and save session
        sess = session.Session.create(model="test", provider="test")
        manager.save(sess)

        # Verify: Session file in expected location
        assert custom_dir.exists()
        session_files = list(custom_dir.glob("*.json"))
        assert len(session_files) == 1
        assert sess.id in session_files[0].name

    def test_env_override_takes_precedence(self) -> None:
        """Environment variables override default config values."""
        # Setup: Set environment variables with nested config syntax
        with _mock.patch.dict(
            _os.environ,
            {
                "BRYNHILD_PROVIDERS__DEFAULT": "ollama",  # Nested: providers.default
                "BRYNHILD_MODELS__DEFAULT": "custom-model",  # Nested: models.default
            },
            clear=False,
        ):
            # Load settings (without .env file)
            settings = config.Settings.construct_without_dotenv()

            # Verify: Environment values used (accessed via property aliases)
            assert settings.provider == "ollama"
            assert settings.model == "custom-model"

    def test_session_list_returns_all_sessions(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """SessionManager lists all saved sessions."""
        # Setup: Create multiple sessions
        sessions_dir = tmp_path / "sessions"
        manager = session.SessionManager(sessions_dir)

        sess1 = session.Session.create(model="model1", provider="prov1")
        sess1.title = "Session One"
        sess2 = session.Session.create(model="model2", provider="prov2")
        sess2.title = "Session Two"
        sess3 = session.Session.create(model="model3", provider="prov3")
        sess3.title = "Session Three"

        manager.save(sess1)
        manager.save(sess2)
        manager.save(sess3)

        # List sessions
        sessions = manager.list_sessions()

        # Verify: All sessions returned
        assert len(sessions) == 3
        session_ids = {s.id for s in sessions}
        assert sess1.id in session_ids
        assert sess2.id in session_ids
        assert sess3.id in session_ids

    def test_load_nonexistent_session_returns_none(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Loading a non-existent session returns None."""
        sessions_dir = tmp_path / "sessions"
        manager = session.SessionManager(sessions_dir)

        # Try to load non-existent session (valid format, but doesn't exist)
        result = manager.load("zzzzzzzz")

        # Verify: Returns None, doesn't crash
        assert result is None

    def test_session_with_tool_messages_persists(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Session with tool-related messages persists correctly."""
        sessions_dir = tmp_path / "sessions"
        manager = session.SessionManager(sessions_dir)

        # Create session with tool messages using supported fields
        sess = session.Session.create(model="test", provider="openrouter")
        sess.add_message("user", "Run a command")
        sess.add_message("assistant", "I'll run that command")
        # Add a tool_use message with tool info
        sess.add_message(
            "tool_use",
            "ls",
            tool_name="Bash",
            tool_input={"command": "ls"},
        )
        # Add tool result
        sess.add_message(
            "tool_result",
            "file1.txt\nfile2.txt",
            tool_result="file1.txt\nfile2.txt",
        )
        sess.add_message("assistant", "Here are the files")

        # Save and reload
        manager.save(sess)
        loaded = manager.load(sess.id)

        # Verify: Messages preserved
        assert loaded is not None
        assert len(loaded.messages) == 5

        # Verify tool_use message
        tool_use_msg = loaded.messages[2]
        assert tool_use_msg.role == "tool_use"
        assert tool_use_msg.tool_name == "Bash"

    def test_session_timestamps_preserved(
        self,
        tmp_path: _pathlib.Path,
    ) -> None:
        """Session timestamps are preserved through save/load."""
        sessions_dir = tmp_path / "sessions"
        manager = session.SessionManager(sessions_dir)

        # Create session
        sess = session.Session.create(model="test", provider="test")
        original_created = sess.created_at
        sess.add_message("user", "test")

        # Save and reload
        manager.save(sess)
        loaded = manager.load(sess.id)

        # Verify: Timestamps preserved
        assert loaded is not None
        assert loaded.created_at == original_created
