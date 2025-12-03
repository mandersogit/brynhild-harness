"""
Session management implementation.

Sessions track conversation history and can be persisted to disk for resumption.
"""

from __future__ import annotations

import dataclasses as _dataclasses
import datetime as _datetime
import json as _json
import pathlib as _pathlib
import secrets as _secrets
import string as _string
import typing as _typing


def generate_session_id() -> str:
    """Generate a unique session ID (8 character alphanumeric)."""
    alphabet = _string.ascii_lowercase + _string.digits
    return "".join(_secrets.choice(alphabet) for _ in range(8))


class InvalidSessionIdError(ValueError):
    """Raised when a session ID has an invalid format."""

    pass


def validate_session_id(session_id: str) -> str:
    """Validate session ID format to prevent path traversal attacks.

    Session IDs can be either:
    - Legacy format: exactly 8 lowercase alphanumeric characters
    - Named format: 1-100 characters of [a-zA-Z0-9_-]

    This prevents path traversal attacks like '../../../etc/passwd'.

    Args:
        session_id: The session ID to validate.

    Returns:
        The validated session ID (unchanged if valid).

    Raises:
        InvalidSessionIdError: If the session ID format is invalid.
    """
    import re as _re

    # Legacy 8-char format OR named format (alphanumeric, hyphens, underscores)
    if _re.match(r"^[a-z0-9]{8}$", session_id):
        return session_id

    if _re.match(r"^[a-zA-Z0-9_-]{1,100}$", session_id):
        return session_id

    raise InvalidSessionIdError(
        f"Invalid session ID: '{session_id}'. "
        "Session IDs must be alphanumeric with hyphens/underscores (max 100 chars)."
    )


def generate_session_name() -> str:
    """Generate a timestamped session name.

    Format: session-YYYYMMDD-HHMMSS
    """
    now = _datetime.datetime.now(_datetime.UTC)
    return f"session-{now.strftime('%Y%m%d-%H%M%S')}"


@_dataclasses.dataclass
class Message:
    """A single message in the conversation."""

    role: _typing.Literal["user", "assistant", "system", "tool_use", "tool_result"]
    content: str
    timestamp: str = _dataclasses.field(
        default_factory=lambda: _datetime.datetime.now(_datetime.UTC).isoformat()
    )

    # Optional fields for tool messages
    tool_name: str | None = None
    tool_input: dict[str, _typing.Any] | None = None
    tool_result: str | None = None

    def to_dict(self) -> dict[str, _typing.Any]:
        """Convert to dictionary for serialization."""
        d: dict[str, _typing.Any] = {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }
        if self.tool_name:
            d["tool_name"] = self.tool_name
        if self.tool_input:
            d["tool_input"] = self.tool_input
        if self.tool_result:
            d["tool_result"] = self.tool_result
        return d

    @classmethod
    def from_dict(cls, data: dict[str, _typing.Any]) -> Message:
        """Create from dictionary."""
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=data.get(
                "timestamp",
                _datetime.datetime.now(_datetime.UTC).isoformat(),
            ),
            tool_name=data.get("tool_name"),
            tool_input=data.get("tool_input"),
            tool_result=data.get("tool_result"),
        )


@_dataclasses.dataclass
class Session:
    """
    A conversation session that can be persisted and resumed.

    Attributes:
        id: Unique session identifier
        cwd: Working directory when session was created
        created_at: ISO timestamp of session creation
        updated_at: ISO timestamp of last update
        model: Model used for this session
        provider: Provider used for this session
        messages: List of messages in the conversation
        tool_metrics: Accumulated tool usage metrics (optional)
    """

    id: str
    cwd: str
    created_at: str
    updated_at: str
    model: str
    provider: str
    messages: list[Message] = _dataclasses.field(default_factory=list)

    # Metadata
    title: str | None = None  # Auto-generated or user-set title

    # Tool metrics (accumulated during session)
    # Format: {tool_name: {call_count, success_count, failure_count, total_duration_ms, ...}}
    tool_metrics: dict[str, dict[str, _typing.Any]] | None = None

    @classmethod
    def create(
        cls,
        cwd: _pathlib.Path | str | None = None,
        model: str = "openai/gpt-oss-120b",
        provider: str = "openrouter",
    ) -> Session:
        """Create a new session."""
        now = _datetime.datetime.now(_datetime.UTC).isoformat()
        return cls(
            id=generate_session_id(),
            cwd=str(cwd or _pathlib.Path.cwd()),
            created_at=now,
            updated_at=now,
            model=model,
            provider=provider,
            messages=[],
        )

    def add_message(
        self,
        role: _typing.Literal["user", "assistant", "system", "tool_use", "tool_result"],
        content: str,
        **kwargs: _typing.Any,
    ) -> Message:
        """Add a message to the session."""
        msg = Message(role=role, content=content, **kwargs)
        self.messages.append(msg)
        self.updated_at = _datetime.datetime.now(_datetime.UTC).isoformat()
        return msg

    def to_dict(self) -> dict[str, _typing.Any]:
        """Convert to dictionary for JSON serialization."""
        d: dict[str, _typing.Any] = {
            "id": self.id,
            "cwd": self.cwd,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "model": self.model,
            "provider": self.provider,
            "title": self.title,
            "messages": [m.to_dict() for m in self.messages],
        }
        if self.tool_metrics:
            d["tool_metrics"] = self.tool_metrics
        return d

    @classmethod
    def from_dict(cls, data: dict[str, _typing.Any]) -> Session:
        """Create from dictionary."""
        messages = [Message.from_dict(m) for m in data.get("messages", [])]
        return cls(
            id=data["id"],
            cwd=data["cwd"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            model=data["model"],
            provider=data["provider"],
            title=data.get("title"),
            messages=messages,
            tool_metrics=data.get("tool_metrics"),
        )

    def summary(self) -> dict[str, _typing.Any]:
        """Get a summary of the session (for listing)."""
        return {
            "id": self.id,
            "cwd": self.cwd,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "model": self.model,
            "provider": self.provider,
            "title": self.title,
            "message_count": len(self.messages),
        }


class SessionManager:
    """
    Manages session persistence and retrieval.

    Sessions are stored as JSON files in the sessions directory.
    """

    def __init__(self, sessions_dir: _pathlib.Path) -> None:
        """Initialize with sessions directory path."""
        self.sessions_dir = sessions_dir

    def _ensure_dir(self) -> None:
        """Ensure sessions directory exists."""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> _pathlib.Path:
        """Get path to session file.

        Args:
            session_id: Session ID (validated).

        Returns:
            Path to the session JSON file.

        Raises:
            InvalidSessionIdError: If session_id format is invalid.
        """
        validate_session_id(session_id)
        return self.sessions_dir / f"{session_id}.json"

    def exists(self, session_id: str) -> bool:
        """Check if a session exists."""
        try:
            path = self._session_path(session_id)
            return path.exists()
        except InvalidSessionIdError:
            return False

    def rename(self, old_id: str, new_id: str) -> bool:
        """Rename a session.

        Args:
            old_id: Current session ID.
            new_id: New session ID.

        Returns:
            True if renamed successfully.

        Raises:
            InvalidSessionIdError: If either ID format is invalid.
            FileNotFoundError: If old session doesn't exist.
            FileExistsError: If new session already exists.
        """
        old_path = self._session_path(old_id)
        new_path = self._session_path(new_id)

        if not old_path.exists():
            raise FileNotFoundError(f"Session not found: {old_id}")
        if new_path.exists():
            raise FileExistsError(f"Session already exists: {new_id}")

        # Load, update ID, save with new name, delete old
        session = self.load(old_id)
        if session is None:
            raise FileNotFoundError(f"Failed to load session: {old_id}")

        session.id = new_id
        session.updated_at = _datetime.datetime.now(_datetime.UTC).isoformat()
        self.save(session)
        old_path.unlink()
        return True

    def save(self, session: Session) -> _pathlib.Path:
        """Save session to disk."""
        self._ensure_dir()
        path = self._session_path(session.id)
        path.write_text(_json.dumps(session.to_dict(), indent=2))
        return path

    def load(self, session_id: str) -> Session | None:
        """Load session from disk by ID."""
        path = self._session_path(session_id)
        if not path.exists():
            return None

        try:
            data = _json.loads(path.read_text())
            return Session.from_dict(data)
        except (_json.JSONDecodeError, KeyError, TypeError):
            return None

    def delete(self, session_id: str) -> bool:
        """Delete session from disk."""
        path = self._session_path(session_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_sessions(self) -> list[Session]:
        """List all sessions, sorted by updated_at (newest first)."""
        self._ensure_dir()
        sessions: list[Session] = []

        for path in self.sessions_dir.glob("*.json"):
            try:
                data = _json.loads(path.read_text())
                sessions.append(Session.from_dict(data))
            except (_json.JSONDecodeError, KeyError, TypeError):
                continue

        # Sort by updated_at, newest first
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    def list_summaries(self) -> list[dict[str, _typing.Any]]:
        """List session summaries (for CLI display)."""
        return [s.summary() for s in self.list_sessions()]

    def get_or_create(
        self,
        session_id: str | None = None,
        **create_kwargs: _typing.Any,
    ) -> Session:
        """Get existing session or create new one."""
        if session_id:
            session = self.load(session_id)
            if session:
                return session

        return Session.create(**create_kwargs)
