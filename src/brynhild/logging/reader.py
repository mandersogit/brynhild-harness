"""
Log reader for parsing and reconstructing conversation context from JSONL logs.

This module provides utilities for:
- Reading and parsing conversation log files
- Reconstructing context at any point in the conversation
- Validating log integrity via content hashes
"""

import dataclasses as _dataclasses
import hashlib as _hashlib
import json as _json
import pathlib as _pathlib
import typing as _typing


@_dataclasses.dataclass
class LogInjection:
    """Record of an injection from the log."""

    source: str
    """Injection source: rules, skill_metadata, skill_trigger, hook, profile, etc."""

    location: str
    """Where injected: system_prompt_prepend, system_prompt_append, message_inject."""

    content: str
    """The injected content."""

    content_hash: str | None = None
    """SHA256 hash prefix of content."""

    origin: str | None = None
    """Source identifier (file path, skill name, etc.)."""

    trigger_type: str | None = None
    """What triggered: startup, keyword, explicit, auto."""

    trigger_match: str | None = None
    """The specific match (keyword, command, etc.)."""

    context_version: int = 0
    """Context version when this injection occurred."""

    event_number: int = 0
    """Event number in the log."""


@_dataclasses.dataclass
class ReconstructedContext:
    """Context reconstructed from log events."""

    system_prompt: str
    """The reconstructed system prompt."""

    context_version: int
    """Context version number."""

    injected_messages: list[str]
    """List of messages injected via message_inject."""


class LogReader:
    """
    Reader for parsing and reconstructing context from log files.

    Usage:
        reader = LogReader("session.jsonl")
        context = reader.get_context_at_version(5)
        print(context.system_prompt)
    """

    def __init__(self, log_path: _pathlib.Path | str) -> None:
        """
        Initialize the log reader.

        Args:
            log_path: Path to the JSONL log file.
        """
        self._log_path = _pathlib.Path(log_path)
        self._events: list[dict[str, _typing.Any]] | None = None

    def _ensure_loaded(self) -> None:
        """Load events if not already loaded."""
        if self._events is None:
            self._events = []
            with open(self._log_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            self._events.append(_json.loads(line))
                        except _json.JSONDecodeError:
                            continue

    def get_events(self) -> list[dict[str, _typing.Any]]:
        """Get all events from the log."""
        self._ensure_loaded()
        assert self._events is not None
        return list(self._events)

    def get_injections(self) -> list[LogInjection]:
        """
        Get all context injections from the log.

        Returns:
            List of LogInjection records in order.
        """
        self._ensure_loaded()
        assert self._events is not None

        injections: list[LogInjection] = []
        for event in self._events:
            if event.get("event_type") == "context_injection":
                injection = LogInjection(
                    source=event.get("source", ""),
                    location=event.get("location", ""),
                    content=event.get("content", ""),
                    content_hash=event.get("content_hash"),
                    origin=event.get("origin"),
                    trigger_type=event.get("trigger_type"),
                    trigger_match=event.get("trigger_match"),
                    context_version=event.get("context_version", 0),
                    event_number=event.get("event_number", 0),
                )
                injections.append(injection)

        return injections

    def get_context_at_version(self, version: int) -> ReconstructedContext | None:
        """
        Reconstruct context at a specific version.

        Args:
            version: The context version to reconstruct.

        Returns:
            ReconstructedContext, or None if version not found.
        """
        self._ensure_loaded()
        assert self._events is not None

        # Find base system prompt
        base_prompt = ""
        for event in self._events:
            if event.get("event_type") == "context_init":
                base_prompt = event.get("base_system_prompt", "")
                break

        if not base_prompt:
            return None

        # Collect injections up to the target version
        prepend_parts: list[str] = []
        append_parts: list[str] = []
        injected_messages: list[str] = []

        for event in self._events:
            if event.get("event_type") != "context_injection":
                continue

            event_version = event.get("context_version", 0)
            if event_version > version:
                break

            content = event.get("content", "")
            location = event.get("location", "")

            if location == "system_prompt_prepend":
                prepend_parts.append(content)
            elif location == "system_prompt_append":
                append_parts.append(content)
            elif location == "message_inject":
                injected_messages.append(content)

        # Build reconstructed system prompt
        parts: list[str] = []
        parts.extend(prepend_parts)
        parts.append(base_prompt)
        parts.extend(append_parts)

        system_prompt = "\n\n".join(parts)

        return ReconstructedContext(
            system_prompt=system_prompt,
            context_version=version,
            injected_messages=injected_messages,
        )

    def get_context_at_event(self, event_number: int) -> ReconstructedContext | None:
        """
        Reconstruct context at a specific event number.

        Args:
            event_number: The event number to reconstruct up to.

        Returns:
            ReconstructedContext, or None if not enough events.
        """
        self._ensure_loaded()
        assert self._events is not None

        # Find the context version at this event
        target_version = 0
        for event in self._events:
            if event.get("event_number", 0) > event_number:
                break
            if "context_version" in event:
                target_version = event["context_version"]

        if target_version == 0:
            return None

        return self.get_context_at_version(target_version)

    def validate(self) -> tuple[bool, list[str]]:
        """
        Validate log integrity by checking content hashes.

        Returns:
            Tuple of (is_valid, list_of_errors).
        """
        self._ensure_loaded()
        assert self._events is not None

        errors: list[str] = []

        for event in self._events:
            if event.get("event_type") != "context_injection":
                continue

            content = event.get("content", "")
            stored_hash = event.get("content_hash")

            if stored_hash:
                computed_hash = _hashlib.sha256(content.encode()).hexdigest()[:16]
                if computed_hash != stored_hash:
                    event_num = event.get("event_number", "?")
                    errors.append(
                        f"Event {event_num}: hash mismatch "
                        f"(stored={stored_hash}, computed={computed_hash})"
                    )

        return len(errors) == 0, errors

    def get_session_info(self) -> dict[str, _typing.Any]:
        """
        Get session metadata from the log.

        Returns:
            Dict with session info (provider, model, start time, etc.).
        """
        self._ensure_loaded()
        assert self._events is not None

        info: dict[str, _typing.Any] = {}

        for event in self._events:
            if event.get("event_type") == "session_start":
                info["session_id"] = event.get("session_id")
                info["provider"] = event.get("provider")
                info["model"] = event.get("model")
                info["start_time"] = event.get("timestamp")
                break

        for event in reversed(self._events):
            if event.get("event_type") == "session_end":
                info["total_events"] = event.get("total_events")
                info["end_time"] = event.get("timestamp")
                break

        return info

    def get_model_switches(self) -> list[dict[str, _typing.Any]]:
        """
        Get all model switch events from the log.

        Returns:
            List of model switch event data.
        """
        self._ensure_loaded()
        assert self._events is not None

        switches: list[dict[str, _typing.Any]] = []
        for event in self._events:
            if event.get("event_type") == "model_switch":
                switches.append({
                    "event_number": event.get("event_number"),
                    "timestamp": event.get("timestamp"),
                    "old_model": event.get("old_model"),
                    "new_model": event.get("new_model"),
                    "old_provider": event.get("old_provider"),
                    "new_provider": event.get("new_provider"),
                    "reason": event.get("reason"),
                    "preserve_context": event.get("preserve_context"),
                })

        return switches

    def get_llm_view_at_turn(self, turn: int) -> dict[str, _typing.Any] | None:
        """
        Reconstruct what the LLM saw at a specific turn.

        Args:
            turn: Turn number (1-indexed, where a turn is user message + response).

        Returns:
            Dict with system_prompt and messages, or None if turn not found.
        """
        self._ensure_loaded()
        assert self._events is not None

        # Count user messages to find the turn
        user_message_count = 0
        target_event_num = 0

        for event in self._events:
            if event.get("event_type") == "user_message":
                user_message_count += 1
                if user_message_count == turn:
                    target_event_num = event.get("event_number", 0)
                    break

        if target_event_num == 0:
            return None

        # Get context at that point
        context = self.get_context_at_event(target_event_num)
        if context is None:
            return None

        # Collect messages up to that point
        messages: list[dict[str, str]] = []
        for event in self._events:
            if event.get("event_number", 0) > target_event_num:
                break

            event_type = event.get("event_type")
            if event_type == "user_message":
                messages.append({
                    "role": "user",
                    "content": event.get("content", ""),
                })
            elif event_type == "assistant_message":
                messages.append({
                    "role": "assistant",
                    "content": event.get("content", ""),
                })

        return {
            "system_prompt": context.system_prompt,
            "messages": messages,
            "injected_messages": context.injected_messages,
        }

