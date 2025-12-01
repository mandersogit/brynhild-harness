"""Tests for session management."""

import pathlib as _pathlib

import pytest as _pytest

import brynhild.session as session
import brynhild.session.session as session_impl


class TestGenerateSessionId:
    """Tests for session ID generation."""

    def test_length(self) -> None:
        """Session ID should be 8 characters."""
        session_id = session.generate_session_id()
        assert len(session_id) == 8

    def test_alphanumeric(self) -> None:
        """Session ID should be alphanumeric lowercase."""
        session_id = session.generate_session_id()
        assert session_id.isalnum()
        assert session_id.islower()

    def test_unique(self) -> None:
        """Session IDs should be unique."""
        ids = {session.generate_session_id() for _ in range(100)}
        assert len(ids) == 100


class TestMessage:
    """Tests for Message dataclass."""

    def test_create_simple(self) -> None:
        """Create a simple message."""
        msg = session_impl.Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.timestamp is not None

    def test_to_dict(self) -> None:
        """Convert message to dictionary."""
        msg = session_impl.Message(role="assistant", content="Hi there")
        d = msg.to_dict()
        assert d["role"] == "assistant"
        assert d["content"] == "Hi there"
        assert "timestamp" in d

    def test_from_dict(self) -> None:
        """Create message from dictionary."""
        d = {"role": "user", "content": "Test", "timestamp": "2024-01-01T00:00:00Z"}
        msg = session_impl.Message.from_dict(d)
        assert msg.role == "user"
        assert msg.content == "Test"

    def test_tool_message(self) -> None:
        """Create a tool use message."""
        msg = session_impl.Message(
            role="tool_use",
            content="",
            tool_name="Bash",
            tool_input={"command": "ls"},
        )
        d = msg.to_dict()
        assert d["tool_name"] == "Bash"
        assert d["tool_input"] == {"command": "ls"}


class TestSession:
    """Tests for Session dataclass."""

    def test_create(self) -> None:
        """Create a new session."""
        sess = session.Session.create(model="test-model", provider="openrouter")
        assert len(sess.id) == 8
        assert sess.model == "test-model"
        assert sess.provider == "openrouter"
        assert sess.messages == []

    def test_create_with_cwd(self, tmp_path: _pathlib.Path) -> None:
        """Create session with specific working directory."""
        sess = session.Session.create(cwd=tmp_path)
        assert sess.cwd == str(tmp_path)

    def test_add_message(self) -> None:
        """Add messages to session."""
        sess = session.Session.create()
        msg = sess.add_message("user", "Hello")
        assert len(sess.messages) == 1
        assert sess.messages[0].content == "Hello"
        assert msg.role == "user"

    def test_to_dict(self) -> None:
        """Convert session to dictionary."""
        sess = session.Session.create()
        sess.add_message("user", "Test")
        d = sess.to_dict()
        assert "id" in d
        assert "messages" in d
        assert len(d["messages"]) == 1

    def test_from_dict(self) -> None:
        """Create session from dictionary."""
        d = {
            "id": "test1234",
            "cwd": "/tmp",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "model": "test-model",
            "provider": "anthropic",
            "messages": [{"role": "user", "content": "Hello"}],
        }
        sess = session.Session.from_dict(d)
        assert sess.id == "test1234"
        assert len(sess.messages) == 1

    def test_summary(self) -> None:
        """Get session summary."""
        sess = session.Session.create()
        sess.add_message("user", "Test")
        summary = sess.summary()
        assert summary["id"] == sess.id
        assert summary["message_count"] == 1


class TestSessionManager:
    """Tests for SessionManager."""

    @_pytest.fixture
    def manager(self, tmp_path: _pathlib.Path) -> session.SessionManager:
        """Create a session manager with temp directory."""
        return session.SessionManager(tmp_path / "sessions")

    def test_save_and_load(self, manager: session.SessionManager) -> None:
        """Save and load a session."""
        sess = session.Session.create()
        sess.add_message("user", "Hello")

        path = manager.save(sess)
        assert path.exists()

        loaded = manager.load(sess.id)
        assert loaded is not None
        assert loaded.id == sess.id
        assert len(loaded.messages) == 1

    def test_load_nonexistent(self, manager: session.SessionManager) -> None:
        """Loading nonexistent session returns None."""
        loaded = manager.load("nonexistent")
        assert loaded is None

    def test_delete(self, manager: session.SessionManager) -> None:
        """Delete a session."""
        sess = session.Session.create()
        manager.save(sess)

        assert manager.delete(sess.id) is True
        assert manager.load(sess.id) is None

    def test_delete_nonexistent(self, manager: session.SessionManager) -> None:
        """Deleting nonexistent session returns False."""
        assert manager.delete("nonexistent") is False

    def test_list_sessions(self, manager: session.SessionManager) -> None:
        """List all sessions."""
        s1 = session.Session.create()
        s2 = session.Session.create()
        manager.save(s1)
        manager.save(s2)

        sessions = manager.list_sessions()
        assert len(sessions) == 2

    def test_list_sessions_empty(self, manager: session.SessionManager) -> None:
        """List sessions when empty."""
        sessions = manager.list_sessions()
        assert sessions == []

    def test_list_summaries(self, manager: session.SessionManager) -> None:
        """List session summaries."""
        sess = session.Session.create()
        sess.add_message("user", "Test")
        manager.save(sess)

        summaries = manager.list_summaries()
        assert len(summaries) == 1
        assert summaries[0]["message_count"] == 1

    def test_get_or_create_new(self, manager: session.SessionManager) -> None:
        """Get or create returns new session when ID not found."""
        sess = manager.get_or_create(model="test-model")
        assert sess.model == "test-model"

    def test_get_or_create_existing(self, manager: session.SessionManager) -> None:
        """Get or create returns existing session when found."""
        original = session.Session.create()
        original.add_message("user", "Original message")
        manager.save(original)

        retrieved = manager.get_or_create(session_id=original.id)
        assert retrieved.id == original.id
        assert len(retrieved.messages) == 1
