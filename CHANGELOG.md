# Changelog

All notable changes to Brynhild will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Context compaction wiring (pending)

## [0.1.0] - 2024-12-04

### Added

#### Core Features
- CLI with `chat`, `config`, `tools`, `plugins`, `session` commands
- Tool system: Bash, Read, Write, Edit, Grep, Glob, Inspect, LearnSkill
- Plugin system: tools, providers, commands, skills, hooks
- OpenRouter and Ollama LLM providers
- Sandbox isolation (macOS sandbox-exec, Linux bubblewrap)
- Session management with save/load/resume
- Model profiles with GPT-OSS optimized prompting

#### UI Features
- Rich terminal UI with Textual
- `--show-thinking` flag for streaming thinking display
- Session info banner showing model/provider/profile
- Token count display in panel footers
- Streaming thinking tokens in real-time

#### Configuration
- Environment-based configuration (`BRYNHILD_*` variables)
- Reasoning format configuration (`BRYNHILD_REASONING_FORMAT`)
- Project-local rules (`.brynhild/`, `AGENTS.md`, `.cursorrules`)

#### Plugin API
- `Tool` base class with `risk_level` and `recovery_policy` properties
- `LLMProvider` base class with `default_reasoning_format` property
- Plugin manifest format (`plugin.yaml`)
- Plugin lifecycle hooks (`PLUGIN_INIT`, `PLUGIN_SHUTDOWN`)
- Tool input validation

#### Resilience
- Tool call recovery from model thinking
- Tool call recovery from content (`[tool_call: ...]` patterns)
- Stuck detection for repetitive tool calls
- Thinking-only response handling with retry

### Documentation
- Plugin development guide
- Plugin API reference
- Tool interface specification
- Migration notes for plugin developers

---

## Version History Summary

| Version | Date | Highlights |
|---------|------|------------|
| 0.1.0 | 2024-12-04 | Initial release |

[Unreleased]: https://github.com/yourorg/brynhild/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yourorg/brynhild/releases/tag/v0.1.0

