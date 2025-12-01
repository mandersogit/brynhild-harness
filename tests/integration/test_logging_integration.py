"""
Integration tests for logging system.

Test IDs from design-plan-phase6.md:
- LI-01: log_context_injection exists
- LI-02: Rules injection logged
- LI-03: Skill trigger logged
- LI-04: Hook injection logged
- LI-05: Log replay reconstructs context
"""

import json as _json
import pathlib as _pathlib

import brynhild.core.context as context
import brynhild.logging.conversation_logger as conversation_logger


class TestLoggingIntegration:
    """Integration tests for logging system."""

    def test_li01_log_context_injection_exists(self) -> None:
        """LI-01: Method implemented on ConversationLogger."""
        logger = conversation_logger.ConversationLogger(enabled=False)

        # Method should exist and be callable
        assert hasattr(logger, "log_context_injection")
        assert callable(logger.log_context_injection)

        # Should also have related methods
        assert hasattr(logger, "log_context_init")
        assert hasattr(logger, "log_context_ready")
        assert hasattr(logger, "log_context_checkpoint")
        assert hasattr(logger, "context_version")

    def test_li02_rules_injection_logged(self, tmp_path: _pathlib.Path) -> None:
        """LI-02: Rules injection produces log event."""
        # Create rules
        (tmp_path / "AGENTS.md").write_text("# Test Rules")

        # Create logger
        log_file = tmp_path / "test.jsonl"
        logger = conversation_logger.ConversationLogger(
            log_file=log_file,
            provider="test",
            model="test-model",
            enabled=True,
        )

        # Build context (triggers rules logging)
        context.build_context(
            "Base prompt",
            project_root=tmp_path,
            logger=logger,
            include_rules=True,
            include_skills=False,
        )
        logger.close()

        # Parse log and find rules injection
        events = _parse_log_file(log_file)
        rules_injections = [
            e for e in events
            if e.get("event_type") == "context_injection"
            and e.get("source") == "rules"
        ]

        assert len(rules_injections) >= 1

    def test_li03_skill_trigger_logged(self, tmp_path: _pathlib.Path) -> None:
        """LI-03: Skill trigger produces log event."""
        log_file = tmp_path / "test.jsonl"
        logger = conversation_logger.ConversationLogger(
            log_file=log_file,
            provider="test",
            model="test-model",
            enabled=True,
        )

        # Manually log a skill trigger
        logger.log_context_init("Base")
        logger.log_context_injection(
            source="skill_trigger",
            location="message_inject",
            content="<skill>test</skill>",
            origin="test-skill",
            trigger_type="keyword",
            trigger_match="test",
        )
        logger.close()

        # Parse log and find skill trigger
        events = _parse_log_file(log_file)
        skill_triggers = [
            e for e in events
            if e.get("event_type") == "context_injection"
            and e.get("source") == "skill_trigger"
        ]

        assert len(skill_triggers) == 1
        assert skill_triggers[0]["origin"] == "test-skill"
        assert skill_triggers[0]["trigger_type"] == "keyword"

    def test_li04_hook_injection_logged(self, tmp_path: _pathlib.Path) -> None:
        """LI-04: Hook inject produces log event."""
        log_file = tmp_path / "test.jsonl"
        logger = conversation_logger.ConversationLogger(
            log_file=log_file,
            provider="test",
            model="test-model",
            enabled=True,
        )

        # Manually log a hook injection
        logger.log_context_init("Base")
        logger.log_context_injection(
            source="hook",
            location="message_inject",
            content="Hook guidance content",
            origin="pre_tool_use",
            trigger_type="auto",
        )
        logger.close()

        # Parse log and find hook injection
        events = _parse_log_file(log_file)
        hook_injections = [
            e for e in events
            if e.get("event_type") == "context_injection"
            and e.get("source") == "hook"
        ]

        assert len(hook_injections) == 1
        assert hook_injections[0]["origin"] == "pre_tool_use"


class TestLogReplay:
    """Tests for log replay and context reconstruction."""

    def test_li05_log_replay_reconstructs_context(
        self, tmp_path: _pathlib.Path
    ) -> None:
        """LI-05: Parsing log file gives full context sequence."""
        log_file = tmp_path / "test.jsonl"
        logger = conversation_logger.ConversationLogger(
            log_file=log_file,
            provider="test",
            model="test-model",
            enabled=True,
        )

        # Simulate a session with multiple injections
        logger.log_context_init("You are Brynhild.")
        logger.log_context_injection(
            source="rules",
            location="system_prompt_prepend",
            content="# Project Rules\nUse Python.",
            origin="/project/AGENTS.md",
            trigger_type="startup",
        )
        logger.log_context_injection(
            source="skill_metadata",
            location="system_prompt_append",
            content="Skills: debugging, testing",
            origin="all_skills",
            trigger_type="startup",
        )
        logger.log_context_ready("abc123")
        logger.log_user_message("Hello")
        logger.log_context_injection(
            source="skill_trigger",
            location="message_inject",
            content="<skill>debugging instructions</skill>",
            origin="debugging",
            trigger_type="keyword",
            trigger_match="debug",
        )
        logger.log_assistant_message("Hi! I'll help you debug.")
        logger.close()

        # Use LogReader to reconstruct
        import brynhild.logging.reader as reader

        log_reader = reader.LogReader(log_file)

        # Reconstruct context at version 3 (after skill_metadata)
        ctx_v3 = log_reader.get_context_at_version(3)
        assert ctx_v3 is not None
        assert "You are Brynhild" in ctx_v3.system_prompt
        assert "Project Rules" in ctx_v3.system_prompt
        assert "Skills: debugging" in ctx_v3.system_prompt

        # Reconstruct context at version 4 (after skill trigger)
        ctx_v4 = log_reader.get_context_at_version(4)
        assert ctx_v4 is not None
        assert len(ctx_v4.injected_messages) >= 1
        assert "debugging instructions" in ctx_v4.injected_messages[0]

    def test_get_all_injections(self, tmp_path: _pathlib.Path) -> None:
        """Can get all injections from a log."""
        log_file = tmp_path / "test.jsonl"
        logger = conversation_logger.ConversationLogger(
            log_file=log_file,
            provider="test",
            model="test-model",
            enabled=True,
        )

        logger.log_context_init("Base")
        logger.log_context_injection("rules", "prepend", "Rules content")
        logger.log_context_injection("skill_metadata", "append", "Skills content")
        logger.log_context_injection("hook", "inject", "Hook content")
        logger.close()

        import brynhild.logging.reader as reader

        log_reader = reader.LogReader(log_file)
        injections = log_reader.get_injections()

        assert len(injections) == 3
        sources = [i.source for i in injections]
        assert "rules" in sources
        assert "skill_metadata" in sources
        assert "hook" in sources

    def test_validate_log_integrity(self, tmp_path: _pathlib.Path) -> None:
        """Log validation checks content hashes."""
        log_file = tmp_path / "test.jsonl"
        logger = conversation_logger.ConversationLogger(
            log_file=log_file,
            provider="test",
            model="test-model",
            enabled=True,
        )

        logger.log_context_init("Base")
        logger.log_context_injection("rules", "prepend", "Exact content")
        logger.close()

        import brynhild.logging.reader as reader

        log_reader = reader.LogReader(log_file)

        # Should validate successfully
        is_valid, errors = log_reader.validate()
        assert is_valid
        assert len(errors) == 0


def _parse_log_file(path: _pathlib.Path) -> list[dict]:
    """Helper to parse a JSONL log file."""
    events = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(_json.loads(line))
    return events

