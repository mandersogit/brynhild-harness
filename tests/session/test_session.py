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


class TestValidateSessionId:
    """Tests for session ID validation (path traversal prevention)."""

    def test_valid_session_id(self) -> None:
        """Valid session IDs pass validation."""
        assert session.validate_session_id("abcd1234") == "abcd1234"
        assert session.validate_session_id("00000000") == "00000000"
        assert session.validate_session_id("zzzzzzzz") == "zzzzzzzz"

    def test_generated_ids_are_valid(self) -> None:
        """Generated session IDs always pass validation."""
        for _ in range(100):
            sid = session.generate_session_id()
            assert session.validate_session_id(sid) == sid

    def test_rejects_path_traversal(self) -> None:
        """Rejects path traversal attempts."""
        with _pytest.raises(session.InvalidSessionIdError):
            session.validate_session_id("../../../etc/passwd")

    def test_rejects_relative_path(self) -> None:
        """Rejects relative paths."""
        with _pytest.raises(session.InvalidSessionIdError):
            session.validate_session_id("../foo")

    def test_rejects_absolute_path(self) -> None:
        """Rejects absolute paths."""
        with _pytest.raises(session.InvalidSessionIdError):
            session.validate_session_id("/etc/passwd")

    def test_accepts_short_names(self) -> None:
        """Accepts short session names (1+ chars)."""
        # Named format: 1-100 chars alphanumeric with hyphens/underscores
        assert session.validate_session_id("abc123") == "abc123"
        assert session.validate_session_id("a") == "a"

    def test_accepts_long_names(self) -> None:
        """Accepts longer session names (up to 100 chars)."""
        assert session.validate_session_id("abcd12345") == "abcd12345"
        assert (
            session.validate_session_id("session-2024-01-01-my-project")
            == "session-2024-01-01-my-project"
        )

    def test_rejects_too_long(self) -> None:
        """Rejects IDs over 100 chars."""
        with _pytest.raises(session.InvalidSessionIdError):
            session.validate_session_id("a" * 101)

    def test_accepts_uppercase(self) -> None:
        """Accepts uppercase characters in named format."""
        assert session.validate_session_id("MySession") == "MySession"
        assert session.validate_session_id("ABCD1234") == "ABCD1234"

    def test_accepts_hyphens_underscores(self) -> None:
        """Accepts hyphens and underscores in named format."""
        assert session.validate_session_id("abc-1234") == "abc-1234"
        assert session.validate_session_id("abc_1234") == "abc_1234"
        assert session.validate_session_id("my-session_name") == "my-session_name"

    def test_rejects_special_chars(self) -> None:
        """Rejects special characters (dots, slashes, etc.)."""
        with _pytest.raises(session.InvalidSessionIdError):
            session.validate_session_id("abc.1234")
        with _pytest.raises(session.InvalidSessionIdError):
            session.validate_session_id("abc/1234")
        with _pytest.raises(session.InvalidSessionIdError):
            session.validate_session_id("abc:1234")

    def test_manager_rejects_invalid_on_load(self, tmp_path: _pathlib.Path) -> None:
        """SessionManager.load rejects invalid session IDs."""
        manager = session.SessionManager(tmp_path / "sessions")
        with _pytest.raises(session.InvalidSessionIdError):
            manager.load("../../../etc/passwd")

    def test_manager_rejects_invalid_on_delete(self, tmp_path: _pathlib.Path) -> None:
        """SessionManager.delete rejects invalid session IDs."""
        manager = session.SessionManager(tmp_path / "sessions")
        with _pytest.raises(session.InvalidSessionIdError):
            manager.delete("../malicious")


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
        # Use a valid format ID that doesn't exist
        loaded = manager.load("zzzzzzzz")
        assert loaded is None

    def test_delete(self, manager: session.SessionManager) -> None:
        """Delete a session."""
        sess = session.Session.create()
        manager.save(sess)

        assert manager.delete(sess.id) is True
        assert manager.load(sess.id) is None

    def test_delete_nonexistent(self, manager: session.SessionManager) -> None:
        """Deleting nonexistent session returns False."""
        # Use a valid format ID that doesn't exist
        assert manager.delete("zzzzzzzz") is False

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

    def test_rename(self, manager: session.SessionManager) -> None:
        """Rename a session."""
        sess = session.Session.create()
        sess.add_message("user", "Hello")
        old_id = sess.id
        manager.save(sess)

        # Rename to a new name
        manager.rename(old_id, "my-renamed-session")

        # Old name should not exist
        assert manager.load(old_id) is None

        # New name should exist with same content
        renamed = manager.load("my-renamed-session")
        assert renamed is not None
        assert renamed.id == "my-renamed-session"
        assert len(renamed.messages) == 1

    def test_rename_nonexistent(self, manager: session.SessionManager) -> None:
        """Rename nonexistent session raises error."""
        with _pytest.raises(FileNotFoundError):
            manager.rename("nonexistent", "new-name")

    def test_rename_to_existing(self, manager: session.SessionManager) -> None:
        """Rename to existing name raises error."""
        s1 = session.Session.create()
        s1.id = "session-one"
        manager.save(s1)

        s2 = session.Session.create()
        s2.id = "session-two"
        manager.save(s2)

        with _pytest.raises(FileExistsError):
            manager.rename("session-one", "session-two")

    def test_exists(self, manager: session.SessionManager) -> None:
        """Check if session exists."""
        sess = session.Session.create()
        manager.save(sess)

        assert manager.exists(sess.id) is True
        assert manager.exists("nonexistent") is False


class TestGenerateSessionName:
    """Tests for generate_session_name function."""

    def test_format(self) -> None:
        """Session name has correct format."""
        name = session.generate_session_name()
        assert name.startswith("session-")
        # Format: session-YYYYMMDD-HHMMSS
        parts = name.split("-")
        assert len(parts) == 3
        assert len(parts[1]) == 8  # YYYYMMDD
        assert len(parts[2]) == 6  # HHMMSS

    def test_valid_session_id(self) -> None:
        """Generated session name passes validation."""
        name = session.generate_session_name()
        assert session.validate_session_id(name) == name
