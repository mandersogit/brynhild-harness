# Agent Onboarding: Brynhild

This document helps AI agents working on the Brynhild codebase get up to speed quickly.

## What is Brynhild?

Brynhild is a **modular AI coding assistant for the terminal**. It provides an open-source, extensible platform for AI-assisted coding with:

- Interactive chat with tool use (read/write files, run commands, search code)
- Multiple LLM provider support (OpenRouter, Ollama, plugin providers)
- Plugin system for extending tools, providers, and behaviors
- OS-level sandboxing for safe command execution
- Skills system for domain-specific knowledge

Named after the Norse valkyrie and shieldmaiden.

## Architecture Overview

```
User Input
    ↓
CLI/TUI (brynhild/cli/, brynhild/ui/)
    ↓
ConversationProcessor (brynhild/core/)
    ↓
LLMProvider (brynhild/api/)  ←→  Tools (brynhild/tools/)
    ↓
Response + Tool Results
```

**Core flow:**
1. User sends message
2. `ConversationProcessor` builds context (system prompt, skills, rules)
3. Sends to LLM via provider
4. LLM may request tool use → tools execute in sandbox → results sent back
5. Loop until LLM produces final response

For detailed architecture, see `docs/architecture-overview.md`.

## Directory Structure

```
src/brynhild/
├── api/           # LLM provider implementations (OpenRouter, Ollama)
├── cli/           # Click-based CLI entry points
├── config/        # Settings, model registry, YAML config loading
├── core/          # ConversationProcessor, context building, types
├── hooks/         # Pre/post tool execution hooks
├── plugins/       # Plugin discovery, manifest, registry
├── profiles/      # User profiles (personas, system prompts)
├── session/       # Conversation session persistence
├── skills/        # Skill loading and discovery
├── tools/         # Tool implementations (Bash, Read, Write, etc.)
├── ui/            # TUI components, streaming display
└── utils/         # Shared utilities

tests/             # Test suite (mirrors src/ structure)
docs/              # User-facing documentation
.cursor/rules/     # Workspace rules (auto-injected by Cursor)
```

## Key Conventions

### Import Style

**Always use qualified imports.** Never import symbols directly into the namespace.

```python
# ❌ WRONG
from pathlib import Path
from typing import Any

# ✅ CORRECT
import pathlib as _pathlib      # External: underscore prefix
import typing as _typing        # External: underscore prefix
import brynhild.config as config  # Internal: no underscore
```

See `.cursor/rules/coding-standards.mdc` for full details.

### Python Environment

Always use the project virtual environment:

```bash
./local.venv/bin/python script.py
./local.venv/bin/pip install package
```

For testing/linting, prefer `make` targets (see Testing section). Never use system Python.

### Git Policy

**Never make git commits without explicit user authorization.** Words like "continue" or "proceed" are NOT authorization for git operations.

Read-only git commands (status, log, diff) are always fine.

### Testing

```bash
# Run all tests (except live API tests)
make test

# Run fast unit tests only
make test-fast

# Type checking
make typecheck

# Lint
make lint

# All checks (lint + typecheck + test)
make all

# Single test file
make test-file FILE=tests/path/to_test.py
```

Tests must be honest and non-trivial. Don't silence tests or make assertions that always pass.

### Tool Implementations

Tools inherit from `brynhild.tools.base.Tool` and must implement:
- `name` (property) → str
- `description` (property) → str  
- `input_schema` (property) → dict
- `execute(input: dict)` → ToolResult

See `docs/plugin-tool-interface.md` for details.

## Common Tasks

### Adding a New Tool

1. Create `src/brynhild/tools/my_tool.py` implementing `Tool`
2. Add to `BUILTIN_TOOL_NAMES` in `tools/registry.py`
3. Add tests in `tests/tools/test_my_tool.py`

### Adding a New Provider

1. Create `src/brynhild/api/my_provider.py` implementing `LLMProvider`
2. Register in `api/factory.py`
3. Add tests in `tests/api/`

### Plugin Development

Plugins can extend Brynhild with tools, providers, hooks, and skills.

- Plugin guide: `docs/plugin-development-guide.md`
- Plugin API: `docs/plugin-api-reference.md`
- Entry points: Plugins can be pip-installed via `pyproject.toml` entry points

## Documentation

| Topic | Document |
|-------|----------|
| Architecture | `docs/architecture-overview.md` |
| API Reference | `docs/api-reference.md` |
| Plugin Development | `docs/plugin-development-guide.md` |
| Tool Interface | `docs/plugin-tool-interface.md` |
| Config System | `docs/migration-guide.md` |

## Getting Help

- Check existing documentation in `docs/`
- Read the code — it's the source of truth
- Look for patterns in existing implementations

