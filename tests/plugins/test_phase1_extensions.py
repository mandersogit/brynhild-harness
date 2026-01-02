"""
Tests for Phase 1 plugin extension features.

Tests:
- Gap #2: CONTEXT_BUILD hook event and context injection
- Gap #4: Tool metrics access in POST_TOOL_USE hook
- Gap #5: Logger access in hook context
- Gap #6: Plugin rules contribution
"""

import pathlib as _pathlib
import tempfile as _tempfile

import pytest as _pytest

import brynhild.hooks.events as events
import brynhild.logging as brynhild_logging
import brynhild.plugins.manifest as manifest
import brynhild.plugins.rules as rules
import brynhild.tools.base as tools_base

# Skip reason for disabled rules feature
RULES_DISABLED_REASON = "Rules injection is disabled - see TODO in context.py and rules.py"


class TestContextBuildEvent:
    """Tests for the CONTEXT_BUILD hook event."""

    def test_context_build_event_exists(self) -> None:
        """CONTEXT_BUILD event should exist."""
        assert hasattr(events.HookEvent, "CONTEXT_BUILD")
        assert events.HookEvent.CONTEXT_BUILD.value == "context_build"

    def test_context_build_can_modify(self) -> None:
        """CONTEXT_BUILD event should allow modifications."""
        assert events.HookEvent.CONTEXT_BUILD.can_modify is True

    def test_context_build_cannot_block(self) -> None:
        """CONTEXT_BUILD event should not allow blocking."""
        assert events.HookEvent.CONTEXT_BUILD.can_block is False

    def test_hook_context_has_context_build_fields(self) -> None:
        """HookContext should have fields for CONTEXT_BUILD event."""
        context = events.HookContext(
            event=events.HookEvent.CONTEXT_BUILD,
            session_id="test-session",
            cwd=_pathlib.Path.cwd(),
            base_system_prompt="Test prompt",
            injections_so_far=[{"source": "rules", "content": "test"}],
        )
        assert context.base_system_prompt == "Test prompt"
        assert context.injections_so_far == [{"source": "rules", "content": "test"}]

    def test_hook_context_to_dict_includes_context_build_fields(self) -> None:
        """to_dict should serialize context build fields."""
        context = events.HookContext(
            event=events.HookEvent.CONTEXT_BUILD,
            session_id="test-session",
            cwd=_pathlib.Path.cwd(),
            base_system_prompt="Test prompt",
            injections_so_far=[{"source": "rules", "content": "test"}],
        )
        result = context.to_dict()
        assert result["base_system_prompt"] == "Test prompt"
        assert result["injections_so_far"] == [{"source": "rules", "content": "test"}]


class TestContextInjectionInHookResult:
    """Tests for context injection fields in HookResult."""

    def test_hook_result_has_context_injection_fields(self) -> None:
        """HookResult should have context injection fields."""
        result = events.HookResult(
            context_injection="Custom plugin context",
            context_location="prepend",
        )
        assert result.context_injection == "Custom plugin context"
        assert result.context_location == "prepend"

    def test_hook_result_from_dict_parses_context_injection(self) -> None:
        """from_dict should parse context injection fields."""
        data = {
            "action": "continue",
            "context_injection": "Plugin injected content",
            "context_location": "append",
        }
        result = events.HookResult.from_dict(data)
        assert result.context_injection == "Plugin injected content"
        assert result.context_location == "append"

    def test_hook_result_from_dict_validates_context_location(self) -> None:
        """from_dict should only accept valid context_location values."""
        data = {
            "action": "continue",
            "context_injection": "content",
            "context_location": "invalid",
        }
        result = events.HookResult.from_dict(data)
        assert result.context_location is None  # Invalid values become None

    def test_hook_result_to_dict_includes_context_injection(self) -> None:
        """to_dict should include context injection fields."""
        result = events.HookResult(
            context_injection="Test content",
            context_location="prepend",
        )
        data = result.to_dict()
        assert data["context_injection"] == "Test content"
        assert data["context_location"] == "prepend"


class TestToolMetricsInHookContext:
    """Tests for tool metrics in HookContext (Gap #4)."""

    def test_hook_context_has_tool_metrics_fields(self) -> None:
        """HookContext should have tool_metrics and session_metrics_summary."""
        metrics = tools_base.ToolMetrics(tool_name="TestTool")
        metrics.record_call(success=True, duration_ms=100.0)

        context = events.HookContext(
            event=events.HookEvent.POST_TOOL_USE,
            session_id="test-session",
            cwd=_pathlib.Path.cwd(),
            tool="TestTool",
            tool_metrics=metrics,
            session_metrics_summary={"total_calls": 5},
        )
        assert context.tool_metrics is not None
        assert context.tool_metrics.call_count == 1
        assert context.session_metrics_summary == {"total_calls": 5}

    def test_hook_context_to_dict_includes_metrics(self) -> None:
        """to_dict should serialize tool metrics."""
        metrics = tools_base.ToolMetrics(tool_name="TestTool")
        metrics.record_call(success=True, duration_ms=100.0)

        context = events.HookContext(
            event=events.HookEvent.POST_TOOL_USE,
            session_id="test-session",
            cwd=_pathlib.Path.cwd(),
            tool="TestTool",
            tool_metrics=metrics,
            session_metrics_summary={"total_calls": 5},
        )
        result = context.to_dict()
        assert "tool_metrics" in result
        assert result["tool_metrics"]["tool_name"] == "TestTool"
        assert result["session_metrics_summary"] == {"total_calls": 5}


class TestLoggerInHookContext:
    """Tests for logger access in HookContext (Gap #5)."""

    def test_hook_context_has_logger_field(self) -> None:
        """HookContext should have a logger field."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            logger = brynhild_logging.ConversationLogger(
                log_dir=tmpdir,
                enabled=True,
            )
            try:
                context = events.HookContext(
                    event=events.HookEvent.PRE_TOOL_USE,
                    session_id="test-session",
                    cwd=_pathlib.Path.cwd(),
                    logger=logger,
                )
                assert context.logger is logger
            finally:
                logger.close()

    def test_logger_not_serialized_in_to_dict(self) -> None:
        """Logger should not be included in to_dict (not JSON-able)."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            logger = brynhild_logging.ConversationLogger(
                log_dir=tmpdir,
                enabled=True,
            )
            try:
                context = events.HookContext(
                    event=events.HookEvent.PRE_TOOL_USE,
                    session_id="test-session",
                    cwd=_pathlib.Path.cwd(),
                    logger=logger,
                )
                result = context.to_dict()
                assert "logger" not in result
            finally:
                logger.close()


@_pytest.mark.skip(reason=RULES_DISABLED_REASON)
class TestPluginRulesContribution:
    """Tests for plugin rules contribution (Gap #6)."""

    def test_plugin_manifest_has_rules_field(self) -> None:
        """PluginManifest should have a rules field."""
        m = manifest.PluginManifest(
            name="test-plugin",
            version="1.0.0",
            rules=["coding-standards.md", "security.md"],
        )
        assert m.rules == ["coding-standards.md", "security.md"]

    def test_plugin_has_rules_method(self) -> None:
        """Plugin should have has_rules() method."""
        m = manifest.PluginManifest(
            name="test-plugin",
            version="1.0.0",
            rules=["rules.md"],
        )
        plugin = manifest.Plugin(
            manifest=m,
            path=_pathlib.Path("/fake/path"),
        )
        assert plugin.has_rules() is True

    def test_plugin_has_rules_returns_false_when_empty(self) -> None:
        """has_rules() should return False when no rules declared."""
        m = manifest.PluginManifest(
            name="test-plugin",
            version="1.0.0",
        )
        plugin = manifest.Plugin(
            manifest=m,
            path=_pathlib.Path("/fake/path"),
        )
        assert plugin.has_rules() is False

    def test_plugin_rules_path_property(self) -> None:
        """Plugin should have rules_path property."""
        m = manifest.PluginManifest(
            name="test-plugin",
            version="1.0.0",
        )
        plugin = manifest.Plugin(
            manifest=m,
            path=_pathlib.Path("/fake/path"),
        )
        assert plugin.rules_path == _pathlib.Path("/fake/path/rules")

    def test_plugin_to_dict_includes_rules(self) -> None:
        """to_dict should include rules."""
        m = manifest.PluginManifest(
            name="test-plugin",
            version="1.0.0",
            rules=["rules.md"],
        )
        plugin = manifest.Plugin(
            manifest=m,
            path=_pathlib.Path("/fake/path"),
        )
        data = plugin.to_dict()
        assert data["rules"] == ["rules.md"]


@_pytest.mark.skip(reason=RULES_DISABLED_REASON)
class TestLoadPluginRules:
    """Tests for load_plugin_rules function."""

    def test_load_plugin_rules_returns_empty_for_no_rules(self) -> None:
        """Should return empty list when plugin has no rules."""
        m = manifest.PluginManifest(
            name="test-plugin",
            version="1.0.0",
        )
        plugin = manifest.Plugin(
            manifest=m,
            path=_pathlib.Path("/fake/path"),
        )
        result = rules.load_plugin_rules(plugin)
        assert result == []

    def test_load_plugin_rules_loads_declared_rules(self) -> None:
        """Should load rules declared in manifest."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = _pathlib.Path(tmpdir)
            rules_dir = plugin_path / "rules"
            rules_dir.mkdir()

            # Create a rules file
            rules_file = rules_dir / "coding-standards.md"
            rules_file.write_text("# Coding Standards\n\nAlways use type hints.")

            m = manifest.PluginManifest(
                name="test-plugin",
                version="1.0.0",
                rules=["coding-standards.md"],
            )
            plugin = manifest.Plugin(
                manifest=m,
                path=plugin_path,
            )

            result = rules.load_plugin_rules(plugin)
            assert len(result) == 1
            assert result[0][0] == rules_file
            assert "Coding Standards" in result[0][1]

    def test_load_plugin_rules_adds_md_extension(self) -> None:
        """Should add .md extension if missing."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = _pathlib.Path(tmpdir)
            rules_dir = plugin_path / "rules"
            rules_dir.mkdir()

            # Create a rules file
            rules_file = rules_dir / "standards.md"
            rules_file.write_text("# Standards")

            m = manifest.PluginManifest(
                name="test-plugin",
                version="1.0.0",
                rules=["standards"],  # No .md extension
            )
            plugin = manifest.Plugin(
                manifest=m,
                path=plugin_path,
            )

            result = rules.load_plugin_rules(plugin)
            assert len(result) == 1
            assert result[0][0] == rules_file

    def test_load_plugin_rules_skips_missing_files(self) -> None:
        """Should skip files that don't exist."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = _pathlib.Path(tmpdir)
            rules_dir = plugin_path / "rules"
            rules_dir.mkdir()

            m = manifest.PluginManifest(
                name="test-plugin",
                version="1.0.0",
                rules=["nonexistent.md"],
            )
            plugin = manifest.Plugin(
                manifest=m,
                path=plugin_path,
            )

            result = rules.load_plugin_rules(plugin)
            assert result == []


@_pytest.mark.skip(reason=RULES_DISABLED_REASON)
class TestRulesManagerWithPlugins:
    """Tests for RulesManager plugin integration."""

    def test_rules_manager_accepts_plugins(self) -> None:
        """RulesManager should accept plugins parameter."""
        manager = rules.RulesManager(
            project_root=_pathlib.Path.cwd(),
            plugins=[],
        )
        assert manager._plugins == []

    def test_rules_manager_loads_plugin_rules(self) -> None:
        """RulesManager should load rules from plugins."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = _pathlib.Path(tmpdir) / "my-plugin"
            plugin_path.mkdir()
            rules_dir = plugin_path / "rules"
            rules_dir.mkdir()

            # Create plugin rule
            rules_file = rules_dir / "plugin-rules.md"
            rules_file.write_text("# Plugin Rules\n\nCustom rules from plugin.")

            m = manifest.PluginManifest(
                name="my-plugin",
                version="1.0.0",
                rules=["plugin-rules.md"],
            )
            plugin = manifest.Plugin(
                manifest=m,
                path=plugin_path,
            )

            # Create a temp project with no rules
            project_path = _pathlib.Path(tmpdir) / "project"
            project_path.mkdir()

            manager = rules.RulesManager(
                project_root=project_path,
                include_global=False,
                plugins=[plugin],
            )

            content = manager.load_rules()
            assert "Plugin Rules" in content
            assert "Custom rules from plugin" in content

    def test_rules_manager_plugin_rules_priority(self) -> None:
        """Plugin rules should have medium priority (between global and project)."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            # Create plugin with rules
            plugin_path = _pathlib.Path(tmpdir) / "my-plugin"
            plugin_path.mkdir()
            rules_dir = plugin_path / "rules"
            rules_dir.mkdir()
            (rules_dir / "plugin-rules.md").write_text("# Plugin Rule")

            m = manifest.PluginManifest(
                name="my-plugin",
                version="1.0.0",
                rules=["plugin-rules.md"],
            )
            plugin = manifest.Plugin(manifest=m, path=plugin_path)

            # Create project with rules
            project_path = _pathlib.Path(tmpdir) / "project"
            project_path.mkdir()
            (project_path / "AGENTS.md").write_text("# Project Rule")

            manager = rules.RulesManager(
                project_root=project_path,
                include_global=False,
                plugins=[plugin],
            )

            content = manager.load_rules()
            # Plugin rules should come before project rules
            plugin_pos = content.find("Plugin Rule")
            project_pos = content.find("Project Rule")
            assert plugin_pos < project_pos, "Plugin rules should come before project rules"

    def test_list_rule_files_includes_plugin_source(self) -> None:
        """list_rule_files should indicate plugin source."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = _pathlib.Path(tmpdir) / "my-plugin"
            plugin_path.mkdir()
            rules_dir = plugin_path / "rules"
            rules_dir.mkdir()
            (rules_dir / "rules.md").write_text("# Rules")

            m = manifest.PluginManifest(
                name="my-plugin",
                version="1.0.0",
                rules=["rules.md"],
            )
            plugin = manifest.Plugin(manifest=m, path=plugin_path)

            project_path = _pathlib.Path(tmpdir) / "project"
            project_path.mkdir()

            manager = rules.RulesManager(
                project_root=project_path,
                include_global=False,
                plugins=[plugin],
            )

            files = manager.list_rule_files()
            plugin_rules = [f for f in files if f.get("source") == "plugin"]
            assert len(plugin_rules) == 1
            assert plugin_rules[0]["plugin_name"] == "my-plugin"


class TestLoggerPluginEvent:
    """Tests for log_plugin_event method."""

    def test_logger_has_log_plugin_event_method(self) -> None:
        """ConversationLogger should have log_plugin_event method."""
        with _tempfile.TemporaryDirectory() as tmpdir:
            logger = brynhild_logging.ConversationLogger(
                log_dir=tmpdir,
                enabled=True,
            )
            try:
                # Should not raise
                logger.log_plugin_event(
                    plugin_name="test-plugin",
                    event_type="cache_hit",
                    data={"key": "value"},
                )
            finally:
                logger.close()

    def test_log_plugin_event_writes_to_file(self) -> None:
        """log_plugin_event should write event to log file."""
        import json as _json

        with _tempfile.TemporaryDirectory() as tmpdir:
            logger = brynhild_logging.ConversationLogger(
                log_dir=tmpdir,
                enabled=True,
            )
            logger.log_plugin_event(
                plugin_name="my-plugin",
                event_type="custom_action",
                data={"param": 123},
                metadata={"extra": "info"},
            )
            logger.close()

            # Read the log file
            log_file = logger.file_path
            assert log_file is not None
            content = log_file.read_text()
            lines = [_json.loads(line) for line in content.strip().split("\n")]

            # Log uses "event_type" not "event"
            plugin_events = [e for e in lines if e.get("event_type") == "plugin_event"]
            assert len(plugin_events) == 1
            event = plugin_events[0]
            assert event["plugin_name"] == "my-plugin"
            assert event["plugin_event_type"] == "custom_action"
            assert event["plugin_data"] == {"param": 123}
            assert event["metadata"] == {"extra": "info"}
