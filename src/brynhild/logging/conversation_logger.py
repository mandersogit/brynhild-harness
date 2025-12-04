"""
Conversation logger for Brynhild.

Logs full conversation history to JSONL files for debugging and analysis.
"""

import datetime as _datetime
import hashlib as _hashlib
import json as _json
import pathlib as _pathlib
import typing as _typing


class ConversationLogger:
    """
    Logs conversation events to a JSONL file.

    Each line in the file is a JSON object representing an event:
    - session_start: Session metadata (model, provider, timestamp)
    - system_prompt: The system prompt sent to the model
    - user_message: User's input
    - assistant_message: Assistant's response
    - tool_call: Tool invocation request
    - tool_result: Result of tool execution
    - error: Error events
    - session_end: Session completion

    Usage:
        logger = ConversationLogger(log_dir="/tmp", provider="openrouter", model="qwen/qwen3-32b")
        logger.log_system_prompt("You are Brynhild...")
        logger.log_user_message("Hello")
        logger.log_assistant_message("Hi there!")
        logger.close()
    """

    def __init__(
        self,
        *,
        log_dir: _pathlib.Path | str | None = None,
        log_file: _pathlib.Path | str | None = None,
        private_mode: bool = True,
        provider: str = "unknown",
        model: str = "unknown",
        enabled: bool = True,
    ) -> None:
        """
        Initialize the conversation logger.

        Args:
            log_dir: Directory for log files (default: /tmp/brynhild-logs-{user}).
            log_file: Explicit log file path (overrides log_dir + auto name).
            private_mode: If True, set log directory to drwx------ (0o700).
            provider: LLM provider name.
            model: Model name.
            enabled: Whether logging is enabled.
        """
        self._enabled = enabled
        self._provider = provider
        self._model = model
        self._file: _typing.TextIO | None = None
        self._file_path: _pathlib.Path | None = None
        self._session_id = _datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self._event_count = 0
        self._context_version = 0

        if not enabled:
            return

        # Determine log file path
        if log_file:
            self._file_path = _pathlib.Path(log_file)
        else:
            # Use log_dir with auto-generated filename
            base_dir = _pathlib.Path(log_dir) if log_dir else _pathlib.Path("/tmp/brynhild-logs")

            # Create directory if needed
            base_dir.mkdir(parents=True, exist_ok=True)

            # Lock down permissions if private_mode (drwx------)
            if private_mode:
                import os as _os
                _os.chmod(base_dir, 0o700)

            # Generate filename with timestamp
            filename = f"brynhild_{self._session_id}.jsonl"
            self._file_path = base_dir / filename

        # Open the file (noqa: held as instance state, closed in close())
        self._file = open(self._file_path, "w", encoding="utf-8")  # noqa: SIM115

        # Log session start
        self._write_event(
            "session_start",
            {
                "session_id": self._session_id,
                "provider": provider,
                "model": model,
            },
        )

    def _write_event(
        self,
        event_type: str,
        data: dict[str, _typing.Any],
    ) -> None:
        """Write an event to the log file."""
        if not self._enabled or not self._file:
            return

        self._event_count += 1
        event = {
            "timestamp": _datetime.datetime.now().isoformat(),
            "event_number": self._event_count,
            "event_type": event_type,
            **data,
        }

        try:
            self._file.write(_json.dumps(event, default=str) + "\n")
            self._file.flush()  # Ensure immediate write for crash safety
        except OSError:
            # Silently ignore write errors - logging shouldn't break the app
            pass

    def log_system_prompt(self, prompt: str) -> None:
        """Log the system prompt (legacy method).

        For Phase 6+, prefer log_context_init() + log_context_injection() + log_context_ready().
        This method acts as an adapter for backwards compatibility.
        """
        if self._context_version == 0:
            self.log_context_init(prompt)
            self.log_context_ready()
        else:
            # Already initialized, just log as-is for backwards compatibility
            self._write_event("system_prompt", {"content": prompt})

    def log_user_message(self, content: str) -> None:
        """Log a user message."""
        self._write_event("user_message", {"content": content})

    def log_assistant_message(
        self,
        content: str,
        thinking: str | None = None,
    ) -> None:
        """Log an assistant message."""
        event_data: dict[str, _typing.Any] = {"content": content}
        if thinking:
            event_data["thinking"] = thinking
        self._write_event("assistant_message", event_data)

    def log_thinking(self, content: str) -> None:
        """Log reasoning/thinking trace."""
        self._write_event("thinking", {"content": content})

    def log_assistant_stream_start(self) -> None:
        """Log the start of a streaming response."""
        self._write_event("assistant_stream_start", {})

    def log_assistant_stream_end(
        self,
        content: str,
        thinking: str | None = None,
    ) -> None:
        """Log the end of a streaming response with full content."""
        event_data: dict[str, _typing.Any] = {"content": content}
        if thinking:
            event_data["thinking"] = thinking
        self._write_event("assistant_stream_end", event_data)

    def log_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, _typing.Any],
        tool_id: str | None = None,
    ) -> None:
        """Log a tool call request."""
        self._write_event(
            "tool_call",
            {
                "tool_name": tool_name,
                "tool_input": tool_input,
                "tool_id": tool_id,
            },
        )

    def log_tool_result(
        self,
        tool_name: str,
        success: bool,
        output: str | None = None,
        error: str | None = None,
        tool_id: str | None = None,
        duration_ms: float | None = None,
    ) -> None:
        """Log a tool execution result."""
        data: dict[str, _typing.Any] = {
            "tool_name": tool_name,
            "success": success,
            "output": output,
            "error": error,
            "tool_id": tool_id,
        }
        if duration_ms is not None:
            data["duration_ms"] = round(duration_ms, 2)
        self._write_event("tool_result", data)

    def log_error(self, error: str, context: str | None = None) -> None:
        """Log an error event."""
        self._write_event(
            "error",
            {
                "error": error,
                "context": context,
            },
        )

    def log_event(self, event_type: str, **kwargs: _typing.Any) -> None:
        """Log a generic event with arbitrary data.

        Use this for events that don't have a dedicated logging method.
        All kwargs are included in the event data.

        Args:
            event_type: The event type string (e.g., "tool_call_recovered").
            **kwargs: Arbitrary key-value pairs to include in the event.
        """
        self._write_event(event_type, dict(kwargs))

    def log_usage(
        self,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Log token usage."""
        self._write_event(
            "usage",
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        )

    def log_tool_metrics(
        self,
        metrics: dict[str, dict[str, _typing.Any]],
    ) -> None:
        """
        Log tool metrics summary.

        Called at end of session to record cumulative tool statistics.

        Args:
            metrics: Dictionary of tool name -> metrics dict from MetricsCollector.to_dict()
        """
        # Calculate summary
        total_calls = sum(m.get("call_count", 0) for m in metrics.values())
        total_success = sum(m.get("success_count", 0) for m in metrics.values())
        total_duration = sum(m.get("total_duration_ms", 0) for m in metrics.values())

        self._write_event(
            "tool_metrics",
            {
                "tools": metrics,
                "summary": {
                    "total_calls": total_calls,
                    "total_success": total_success,
                    "total_failures": total_calls - total_success,
                    "success_rate": (total_success / total_calls * 100.0) if total_calls else 0.0,
                    "total_duration_ms": round(total_duration, 2),
                    "tools_used": len(metrics),
                },
            },
        )

    def log_raw_request(self, data: dict[str, _typing.Any]) -> None:
        """Log raw API request (for debugging)."""
        self._write_event("raw_request", {"data": data})

    def log_raw_response(self, data: dict[str, _typing.Any]) -> None:
        """Log raw API response (for debugging)."""
        self._write_event("raw_response", {"data": data})

    # =========================================================================
    # Context Logging (Phase 6)
    # =========================================================================

    def log_context_init(self, base_system_prompt: str) -> None:
        """
        Log the base system prompt at session start.

        Called once at the beginning of a session, before any injections.
        Sets context_version to 1.

        Args:
            base_system_prompt: The base system prompt before any modifications.
        """
        self._context_version = 1
        self._write_event("context_init", {
            "base_system_prompt": base_system_prompt,
            "context_version": self._context_version,
        })

    def log_context_injection(
        self,
        source: str,
        location: str,
        content: str,
        *,
        origin: str | None = None,
        trigger_type: str | None = None,
        trigger_match: str | None = None,
        metadata: dict[str, _typing.Any] | None = None,
    ) -> None:
        """
        Log a context injection event.

        Called whenever content is injected into the conversation context.
        Increments context_version.

        Args:
            source: Injection source type:
                - "rules": Rule file content
                - "skill_metadata": Skill descriptions at startup
                - "skill_trigger": Full skill body when triggered
                - "hook": Hook inject_system_message
                - "stuck_detection": StuckDetector suggestion
                - "profile": Profile system_prompt_prefix/suffix/patterns
            location: Where content is injected:
                - "system_prompt_prepend": Before base system prompt
                - "system_prompt_append": After base system prompt
                - "message_inject": As a conversation message
            content: The actual content being injected.
            origin: Source identifier (file path, skill name, hook name, etc.).
            trigger_type: What triggered this injection:
                - "startup": Automatic at session start
                - "keyword": Keyword match in user message
                - "explicit": User command like /skill
                - "auto": Automatic (stuck detection, etc.)
            trigger_match: The specific match (keyword, command, etc.).
            metadata: Additional source-specific data.
        """
        self._context_version += 1
        self._write_event("context_injection", {
            "context_version": self._context_version,
            "source": source,
            "location": location,
            "content": content,
            "content_hash": _hashlib.sha256(content.encode()).hexdigest()[:16],
            "origin": origin,
            "trigger_type": trigger_type,
            "trigger_match": trigger_match,
            "metadata": metadata,
        })

    def log_context_ready(self, system_prompt_hash: str | None = None) -> None:
        """
        Log that context preparation is complete.

        Called after all startup injections, before the first LLM call.

        Args:
            system_prompt_hash: Hash of the final system prompt (optional).
        """
        self._write_event("context_ready", {
            "context_version": self._context_version,
            "system_prompt_hash": system_prompt_hash,
        })

    def log_context_checkpoint(
        self,
        full_system_prompt: str,
        injected_messages: list[str] | None = None,
    ) -> None:
        """
        Log a full context checkpoint (optional).

        Can be called periodically or on-demand for debugging.
        Does NOT increment context_version.

        Args:
            full_system_prompt: The complete current system prompt.
            injected_messages: List of injected message contents (if any).
        """
        self._write_event("context_checkpoint", {
            "context_version": self._context_version,
            "full_system_prompt": full_system_prompt,
            "full_system_prompt_hash": _hashlib.sha256(
                full_system_prompt.encode()
            ).hexdigest()[:16],
            "injected_messages": injected_messages,
        })

    @property
    def context_version(self) -> int:
        """Current context version number."""
        return self._context_version

    # =========================================================================
    # Skill Triggering
    # =========================================================================

    def log_skill_triggered(
        self,
        skill_name: str,
        skill_content: str,
        trigger_type: str,
        *,
        trigger_match: str | None = None,
        metadata: dict[str, _typing.Any] | None = None,
    ) -> None:
        """
        Log that a skill was triggered and its body injected.

        This is a convenience wrapper around log_context_injection
        specifically for skill triggering.

        Args:
            skill_name: Name of the triggered skill.
            skill_content: Full skill body content.
            trigger_type: How the skill was triggered:
                - "explicit": User used /skill command
                - "auto": Automatic keyword matching
            trigger_match: The match that triggered (e.g., "/skill commit-helper").
            metadata: Additional metadata.
        """
        self.log_context_injection(
            source="skill_trigger",
            location="message_inject",
            content=skill_content,
            origin=skill_name,
            trigger_type=trigger_type,
            trigger_match=trigger_match,
            metadata=metadata,
        )

    # =========================================================================
    # Model Switching (Future Extension)
    # =========================================================================

    def log_model_switch(
        self,
        new_model: str,
        new_provider: str | None = None,
        reason: str = "user",
        *,
        preserve_context: bool = True,
        metadata: dict[str, _typing.Any] | None = None,
    ) -> None:
        """
        Log a model switch event.

        Called when the model changes mid-conversation.

        Args:
            new_model: New model identifier.
            new_provider: New provider (if changed).
            reason: Why the switch happened:
                - "user": User explicitly requested
                - "fallback": Primary failed, falling back
                - "weak": Cheap model for simple task
                - "capable": Strong model for complex task
                - "profile": Profile specifies different model
                - "limit": Context window exceeded
            preserve_context: Whether context is preserved (vs rebuilt).
            metadata: Additional switch-specific data.
        """
        self._write_event("model_switch", {
            "context_version": self._context_version,
            "old_model": self._model,
            "old_provider": self._provider,
            "new_model": new_model,
            "new_provider": new_provider,
            "reason": reason,
            "preserve_context": preserve_context,
            "metadata": metadata,
        })
        # Update internal state
        self._model = new_model
        if new_provider:
            self._provider = new_provider

    def log_context_reset(
        self,
        new_base_system_prompt: str,
        reason: str,
        *,
        preserve_messages: bool = True,
        metadata: dict[str, _typing.Any] | None = None,
    ) -> None:
        """
        Log a context reset event.

        Called when context is substantially rebuilt (e.g., new model
        requires different prompt format).

        Resets context_version to 1 and logs the new base prompt.

        Args:
            new_base_system_prompt: The new base system prompt.
            reason: Why context was reset (e.g., "model_switch", "user_clear").
            preserve_messages: Whether conversation messages are kept.
            metadata: Additional reset-specific data.
        """
        old_version = self._context_version
        self._context_version = 1
        self._write_event("context_reset", {
            "old_context_version": old_version,
            "new_context_version": 1,
            "reason": reason,
            "preserve_messages": preserve_messages,
            "new_base_system_prompt": new_base_system_prompt,
            "new_base_prompt_hash": _hashlib.sha256(
                new_base_system_prompt.encode()
            ).hexdigest()[:16],
            "metadata": metadata,
        })

    def log_plugin_event(
        self,
        plugin_name: str,
        event_type: str,
        data: dict[str, _typing.Any] | None = None,
        *,
        metadata: dict[str, _typing.Any] | None = None,
    ) -> None:
        """
        Log a custom plugin event.

        Allows plugins to log arbitrary events for debugging and analysis.

        Args:
            plugin_name: Name of the plugin logging the event.
            event_type: Type of event (plugin-defined, e.g., "cache_hit").
            data: Event-specific data.
            metadata: Additional metadata.
        """
        self._write_event("plugin_event", {
            "plugin_name": plugin_name,
            "plugin_event_type": event_type,
            "plugin_data": data or {},
            "metadata": metadata,
        })

    @property
    def file_path(self) -> _pathlib.Path | None:
        """Get the log file path."""
        return self._file_path

    @property
    def enabled(self) -> bool:
        """Check if logging is enabled."""
        return self._enabled

    def close(self) -> None:
        """Close the log file."""
        if not self._enabled or not self._file:
            return

        self._write_event(
            "session_end",
            {
                "total_events": self._event_count,
            },
        )

        try:
            self._file.close()
        except OSError:
            pass
        finally:
            self._file = None

    def __enter__(self) -> "ConversationLogger":
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: _typing.Any,
    ) -> None:
        """Context manager exit."""
        if exc_type:
            self.log_error(str(exc_val), context=f"Exception: {exc_type.__name__}")
        self.close()

