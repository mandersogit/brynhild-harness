# Brynhild Architecture Overview

> **Brynhild** is a modular AI coding assistant for the terminal, named after the Norse valkyrie and shieldmaiden. This document provides a comprehensive technical overview of the system architecture.

## Table of Contents

1. [High-Level Architecture](#high-level-architecture)
2. [Core Data Flow](#core-data-flow)
3. [Module Overview](#module-overview)
4. [Key Abstractions](#key-abstractions)
5. [Extension System](#extension-system)
6. [Security Model](#security-model)
7. [Configuration System](#configuration-system)
8. [UI Architecture](#ui-architecture)
9. [Appendix: Module Reference](#appendix-module-reference)

---

## High-Level Architecture

Brynhild follows a layered architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Interface Layer                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │  CLI (Click) │  │  TUI (Textual)│  │  JSON Output Mode    │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                    Conversation Processing Layer                 │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  ConversationProcessor (unified streaming & tool loop)      ││
│  │  ConversationCallbacks (UI abstraction)                     ││
│  └─────────────────────────────────────────────────────────────┘│
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  ContextBuilder │  │  SessionManager │  │  HookManager    │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                       Provider Layer (API)                       │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  LLMProvider (abstract base)                                ││
│  └─────────────────────────────────────────────────────────────┘│
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  OpenRouter     │  │  Ollama         │  │  Plugin Providers│ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                        Tool Layer                                │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  ToolRegistry                                               ││
│  └─────────────────────────────────────────────────────────────┘│
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────────────┐ │
│  │  Bash  │ │  Read  │ │  Write │ │  Edit  │ │  Plugin Tools  │ │
│  │  Grep  │ │  Glob  │ │Inspect │ │LearnSk │ │                │ │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                     Sandbox & Security Layer                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  SandboxConfig  │  │  Path Validation│  │  OS Sandbox     │  │
│  │                 │  │                 │  │  (macOS/Linux)  │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Modularity**: Each component has a single responsibility and clear interfaces
2. **Extensibility**: Plugins can add tools, providers, commands, hooks, and skills
3. **Security-First**: OS-level sandboxing, path validation, and permission controls
4. **Provider-Agnostic**: Abstract `LLMProvider` interface allows multiple backends
5. **Progressive Enhancement**: Skills and rules are loaded progressively to minimize token usage

---

## Core Data Flow

### Conversation Flow

```
User Input
    │
    ▼
┌─────────────────────────────────────┐
│         Preprocessing               │
│  • Skill triggers (/skill command)  │
│  • Context building (rules, skills) │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│    ConversationProcessor Loop       │
│  ┌─────────────────────────────────┐│
│  │ 1. Build messages + system      ││
│  │ 2. Call LLM provider (stream)   ││
│  │ 3. Handle tool calls            ││
│  │    └─► Pre-hook → Execute → Post││
│  │ 4. Loop until no more tools     ││
│  │ 5. Return final response        ││
│  └─────────────────────────────────┘│
└─────────────────────────────────────┘
    │
    ▼
Response to User
```

### Tool Execution Flow

```
LLM requests tool use
        │
        ▼
┌───────────────────────┐
│   PRE_TOOL_USE Hook   │ ← Can BLOCK, SKIP, or modify input
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  Permission Check     │ ← User approval (unless auto-approve)
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│   Tool.execute()      │ ← Sandboxed execution
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  POST_TOOL_USE Hook   │ ← Can modify output
└───────────────────────┘
        │
        ▼
Result returned to LLM
```

---

## Module Overview

### `brynhild/` - Package Root

```
brynhild/
├── __init__.py          # Public API (Settings, Session, SessionManager)
├── __main__.py          # Entry point
├── constants.py         # DEFAULT_MAX_TOKENS, DEFAULT_MAX_TOOL_ROUNDS
│
├── api/                 # LLM Provider abstraction
├── cli/                 # Command-line interface (Click)
├── config/              # Configuration (pydantic-settings)
├── core/                # Conversation processing
├── hooks/               # Event system & stuck detection
├── logging/             # JSONL conversation logging
├── plugins/             # Plugin system
├── profiles/            # Model-specific configurations
├── session/             # Session persistence
├── skills/              # Knowledge/skill injection
├── tools/               # Tool definitions & sandbox
├── ui/                  # TUI (Textual) & renderers
└── builtin_skills/      # Bundled skills (commit-helper, skill-creator)
```

### Core Modules in Detail

#### `api/` - LLM Provider Abstraction

| File                     | Purpose                                              |
|--------------------------|------------------------------------------------------|
| `base.py`                | `LLMProvider` abstract base class                    |
| `types.py`               | `StreamEvent`, `ToolUse`, `CompletionResponse`, etc. |
| `factory.py`             | `create_provider()` factory function                 |
| `openrouter_provider.py` | OpenRouter implementation                            |
| `ollama_provider.py`     | Ollama (local) implementation                        |

The provider abstraction normalizes different API formats:

```python
class LLMProvider(ABC):
    @property
    def name(self) -> str: ...
    @property
    def model(self) -> str: ...
    
    def supports_tools(self) -> bool: ...
    def supports_reasoning(self) -> bool: ...
    
    async def complete(...) -> CompletionResponse: ...
    async def stream(...) -> AsyncIterator[StreamEvent]: ...
```

#### `core/` - Conversation Processing

| File               | Purpose                                             |
|--------------------|-----------------------------------------------------|
| `conversation.py`  | `ConversationProcessor` - unified conversation loop |
| `context.py`       | `ContextBuilder` - system prompt construction       |
| `prompts.py`       | `get_system_prompt()` - base prompt generation      |
| `types.py`         | `ToolCallDisplay`, `ToolResultDisplay` DTOs         |
| `tool_executor.py` | (Legacy, functionality moved to conversation.py)    |

The `ConversationProcessor` is the heart of the system:

```python
class ConversationProcessor:
    """
    Unified conversation processing for all UI modes.
    
    Handles:
    - Streaming and non-streaming modes
    - Multi-round tool execution
    - Hook dispatch (pre/post tool)
    - Cancellation
    - Message history management
    """
```

#### `tools/` - Tool System

| File               | Purpose                                                 |
|--------------------|---------------------------------------------------------|
| `base.py`          | `Tool` ABC, `ToolResult`, `ToolMetrics`, `SandboxMixin` |
| `registry.py`      | `ToolRegistry`, `build_registry_from_settings()`        |
| `bash.py`          | Shell command execution                                 |
| `file.py`          | `Read`, `Write`, `Edit` tools                           |
| `grep.py`          | Pattern search                                          |
| `glob.py`          | File listing                                            |
| `inspect.py`       | Code structure analysis                                 |
| `skill.py`         | `LearnSkill` tool for model-controlled skill loading    |
| `sandbox.py`       | Path validation, Seatbelt profile generation            |
| `sandbox_linux.py` | bubblewrap (bwrap) integration                          |

Tool interface:

```python
class Tool(ABC):
    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str: ...
    @property
    def input_schema(self) -> dict: ...  # JSON Schema
    
    @property
    def requires_permission(self) -> bool: ...  # Default: True
    @property
    def version(self) -> str: ...              # Optional metadata
    @property
    def categories(self) -> list[str]: ...     # Optional metadata
    
    async def execute(self, input: dict) -> ToolResult: ...
```

#### `hooks/` - Event System

| File            | Purpose                                                     |
|-----------------|-------------------------------------------------------------|
| `events.py`     | `HookEvent` enum, `HookContext`, `HookResult`, `HookAction` |
| `config.py`     | `HooksConfig`, `HookDefinition` from YAML                   |
| `manager.py`    | `HookManager` - event dispatch                              |
| `matching.py`   | Pattern matching for hook conditions                        |
| `stuck.py`      | `StuckDetector` - loop detection                            |
| `compaction.py` | Context compaction (implemented, **not yet integrated**)    |
| `executors/`    | Command, script, and prompt hook executors                  |

Hook events:

| Event                | Timing                | Can Block | Can Modify         |
|----------------------|-----------------------|-----------|--------------------|
| `PLUGIN_INIT`        | Plugin loaded         | No        | No                 |
| `PLUGIN_SHUTDOWN`    | Brynhild exiting      | No        | No                 |
| `SESSION_START`      | New session           | No        | No                 |
| `SESSION_END`        | Session ends          | No        | No                 |
| `PRE_TOOL_USE`       | Before tool execution | **Yes**   | **Yes** (input)    |
| `POST_TOOL_USE`      | After tool execution  | No        | **Yes** (output)   |
| `PRE_MESSAGE`        | Before LLM call       | **Yes**   | **Yes**            |
| `POST_MESSAGE`       | After LLM response    | No        | **Yes**            |
| `USER_PROMPT_SUBMIT` | User submits input    | **Yes**   | **Yes**            |
| `PRE_COMPACT`        | Before compaction     | No        | **Yes** (strategy) |
| `ERROR`              | Error occurred        | No        | No                 |

> **Note**: The `PRE_COMPACT` event is defined but not yet fired. The `ContextCompactor` class in `compaction.py` is fully implemented but not integrated into `ConversationProcessor`. See [Quick Wins](#quick-wins-low-risk-high-value) in the roadmap for integration plan.

#### `plugins/` - Plugin System

| File           | Purpose                                      |
|----------------|----------------------------------------------|
| `manifest.py`  | `PluginManifest`, `Plugin` dataclasses       |
| `discovery.py` | `PluginDiscovery` - finds plugins            |
| `registry.py`  | `PluginRegistry` - enable/disable state      |
| `loader.py`    | `PluginLoader` - validates plugins           |
| `tools.py`     | `ToolLoader` - loads plugin tools            |
| `providers.py` | Plugin LLM provider loading                  |
| `commands.py`  | Slash command loading                        |
| `hooks.py`     | Plugin hook integration                      |
| `rules.py`     | `RulesManager` - AGENTS.md, .cursorrules     |
| `lifecycle.py` | `PLUGIN_INIT`, `PLUGIN_SHUTDOWN` hooks       |
| `stubs.py`     | Official stubs for standalone plugin testing |

Plugin discovery paths (searched in order):

1. `BRYNHILD_PLUGIN_PATH` environment variable
2. `~/.config/brynhild/plugins/` (global)
3. `.brynhild/plugins/` (project)

#### `skills/` - Knowledge System

| File              | Purpose                                   |
|-------------------|-------------------------------------------|
| `skill.py`        | `Skill`, `SkillFrontmatter` from SKILL.md |
| `discovery.py`    | `SkillDiscovery` - finds skills           |
| `registry.py`     | `SkillRegistry` - skill management        |
| `loader.py`       | `SkillLoader` - progressive loading       |
| `preprocessor.py` | `/skill` command processing               |

Skill loading levels:

1. **Level 1 (Metadata)**: Name + description only (~100 tokens per skill)
2. **Level 2 (Body)**: Full SKILL.md content when triggered
3. **Level 3 (References)**: Additional files from `references/` on demand

#### `profiles/` - Model Profiles

| File                 | Purpose                                 |
|----------------------|-----------------------------------------|
| `types.py`           | `ModelProfile` dataclass                |
| `manager.py`         | `ProfileManager` - resolution & loading |
| `builtin/default.py` | Default profile                         |
| `builtin/gpt_oss.py` | GPT-OSS-120B optimized profile          |

Profile resolution order:

1. Exact match by profile name
2. Family match (model name prefix)
3. Default profile

---

## Key Abstractions

### 1. Provider Abstraction (`LLMProvider`)

All LLM interactions go through the abstract `LLMProvider` interface, enabling:

- Multiple backend support (OpenRouter, Ollama, plugins)
- Consistent streaming event format
- Model profile integration
- Connection testing

### 2. Tool Interface (`Tool`)

Tools are the primary way the LLM interacts with the outside world:

```python
@dataclass
class ToolResult:
    success: bool
    output: str
    error: str | None = None
```

The `SandboxMixin` provides path validation for file-based tools.

### 3. Conversation Callbacks

The `ConversationCallbacks` abstract class decouples the conversation loop from UI:

```python
class ConversationCallbacks(ABC):
    async def on_stream_start(self) -> None: ...
    async def on_text_delta(self, text: str) -> None: ...
    async def on_tool_call(self, tool_call: ToolCallDisplay) -> None: ...
    async def request_tool_permission(self, tool_call: ToolCallDisplay) -> bool: ...
    # ... etc
```

This allows the same `ConversationProcessor` to drive both TUI and CLI.

### 4. Hook System

Hooks provide lifecycle interception without modifying core code:

```python
@dataclass
class HookResult:
    action: HookAction  # CONTINUE, BLOCK, or SKIP
    message: str | None = None
    modified_input: dict | None = None  # For PRE_TOOL_USE
    modified_output: str | None = None  # For POST_TOOL_USE
    inject_system_message: str | None = None
```

---

## Extension System

### Plugin Architecture

Plugins can provide:

| Component     | Location            | Description                       |
|---------------|---------------------|-----------------------------------|
| **Tools**     | `tools/*.py`        | Custom tool implementations       |
| **Commands**  | `commands/*.md`     | Slash commands (markdown prompts) |
| **Hooks**     | `hooks.yaml`        | Event handlers                    |
| **Skills**    | `skills/*/SKILL.md` | Knowledge files                   |
| **Providers** | `providers/*.py`    | Custom LLM backends               |

Plugin manifest (`plugin.yaml`):

```yaml
name: my-plugin
version: 1.0.0
description: My awesome plugin

tools:
  - my_tool
commands:
  - build
  - deploy
hooks: true
skills:
  - my-skill
```

### Skill System

Skills are structured knowledge files that the model can request:

```markdown
---
name: commit-helper
description: Git commit message generation and workflow assistance
allowed-tools:
  - Bash
  - Read
---

# Commit Helper Skill

This skill helps with...
```

Skills are:
- **Discovered** from: builtin → global → env → plugin → project
- **Loaded progressively**: metadata first, body on demand
- **Triggered by**: `LearnSkill` tool (model) or `/skill` command (user)

### Rules System

Rules provide project-specific instructions:

| File                 | Purpose                        |
|----------------------|--------------------------------|
| `AGENTS.md`          | Standard multi-framework rules |
| `.cursorrules`       | Cross-tool compatibility       |
| `rules.md`           | Brynhild-specific rules        |
| `.brynhild/rules.md` | Project-local rules            |

Discovery walks from current directory to root, with global rules (`~/.config/brynhild/rules/`) loaded first.

---

## Security Model

### Multi-Layer Protection

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: Path Validation (SandboxConfig)                   │
│  • Write-restricted to project + /tmp                       │
│  • Platform-aware sensitive path blocklists                 │
│  • "Punch-through" for project directory in home block      │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: OS-Level Sandbox                                  │
│  • macOS: sandbox-exec with Seatbelt profiles               │
│  • Linux: bubblewrap (bwrap) with namespace isolation       │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: Permission System                                 │
│  • Tool-level requires_permission flag                      │
│  • User approval dialogs                                    │
│  • Auto-approve mode (--yes, dangerous)                     │
└─────────────────────────────────────────────────────────────┘
```

### Path Validation Logic

For **writes**:
1. Check if path is in ALLOWED directory (project, /tmp) → ALLOW
2. Check if path is in BLOCKED directory (~, /etc, etc.) → BLOCK
3. Otherwise → BLOCK (writes must be to allowed paths)

For **reads**:
1. Check if path is in ALLOWED directory → ALLOW
2. Check if path is in BLOCKED directory → BLOCK
3. Otherwise → ALLOW (needed for /usr, /bin, /System, etc.)

### Sandbox Implementation

**macOS (Seatbelt)**:
```lisp
(version 1)
(deny default)
(allow process-fork)
(allow process-exec)
(allow file-read*)
(deny file-read* (subpath "/Users"))
(allow file-read* (subpath "/path/to/project"))
(allow file-write* (subpath "/path/to/project"))
(allow file-write* (subpath "/tmp"))
(deny network*)
```

**Linux (bubblewrap)**:
```bash
bwrap \
  --ro-bind /usr /usr \
  --ro-bind /lib /lib \
  --bind /project /project \
  --bind /tmp /tmp \
  --unshare-net \
  --die-with-parent \
  /bin/bash -c "command"
```

---

## Configuration System

### Settings (`brynhild.config.Settings`)

Configuration uses layered YAML files with pydantic-settings validation.
Environment variables use double underscores (`__`) for nested paths.

| Setting | Env Var | Default | Description |
|---------|---------|---------|-------------|
| `providers.default` | `BRYNHILD_PROVIDERS__DEFAULT` | `openrouter` | LLM provider |
| `models.default` | `BRYNHILD_MODELS__DEFAULT` | `openai/gpt-oss-120b` | Model name |
| `behavior.max_tokens` | `BRYNHILD_BEHAVIOR__MAX_TOKENS` | `8192` | Response limit |
| `sandbox.enabled` | `BRYNHILD_SANDBOX__ENABLED` | `true` | Enable sandbox |
| `sandbox.allow_network` | `BRYNHILD_SANDBOX__ALLOW_NETWORK` | `false` | Network access |
| `logging.enabled` | `BRYNHILD_LOGGING__ENABLED` | `true` | JSONL logging |

**Config precedence:** Built-in defaults → User config → Project config → Env vars → CLI

### Directory Structure

```
~/.config/brynhild/             # XDG config directory
├── config.yaml                 # User configuration
└── sessions/                   # Session persistence (JSON)

~/.config/brynhild/             # System config directory
├── config.yaml                 # Main configuration
├── plugins.yaml                # Plugin enable/disable state
├── profiles/                   # User-defined profiles (YAML)
├── rules/                      # Global rules (*.md)
├── skills/                     # User skills (*/SKILL.md)
└── plugins/                    # User plugins

.brynhild/                      # Project-local config
├── rules.md                    # Project rules
├── AGENTS.md                   # Standard rules file
├── skills/                     # Project skills
└── plugins/                    # Project plugins

/tmp/brynhild-logs-{username}/  # Conversation logs (JSONL)
```

---

## UI Architecture

### Layered UI System

```
Layer 4: Interactive TUI (Textual)
    │ BrynhildApp - full interactive terminal app
    │ Streaming widgets, permission modals, help screens
    │
Layer 3: Conversation Runner
    │ ConversationRunner - high-level CLI wrapper
    │ Preprocesses skills, manages messages
    │
Layer 2: Renderers (ui/base.py)
    │ Renderer ABC with show_*, finalize methods
    │ Implementations: Rich, Plain, JSON
    │
Layer 1: Core Conversation (core/conversation.py)
    │ ConversationProcessor - provider-agnostic loop
    │ ConversationCallbacks - UI integration points
```

### TUI Components (`ui/app.py`)

| Component                | Purpose                                  |
|--------------------------|------------------------------------------|
| `BrynhildApp`            | Main Textual application                 |
| `TUICallbacks`           | Adapts ConversationCallbacks for Textual |
| `HelpScreen`             | Modal help display                       |
| `PermissionScreen`       | Tool approval dialog                     |
| `StreamingMessageWidget` | Real-time response display               |
| `MessageWidget`          | Static message display                   |

### Keybinding Philosophy

Brynhild uses a leader-key system (Ctrl+T prefix) to avoid conflicts with emacs-style text editing:

- **Ctrl+T → h**: Help
- **Ctrl+T → q**: Quit
- **Ctrl+T → t**: Toggle thinking
- **Ctrl+T → c**: Clear conversation
- **Ctrl+T → p**: Command palette

Reserved emacs keys (never used): Ctrl+A/E/F/B/N/P/D/K/Y/W/U/L/O

---

## Appendix: Module Reference

### Import Conventions

Brynhild follows strict import conventions:

```python
# External: underscore prefix
import pathlib as _pathlib
import typing as _typing
import click as _click

# Internal: NO underscore
import brynhild.config as config
import brynhild.tools.base as tools_base
```

### Key Types

| Type                    | Module                       | Purpose                 |
|-------------------------|------------------------------|-------------------------|
| `Settings`              | `brynhild.config`            | Configuration container |
| `Session`               | `brynhild.session`           | Conversation state      |
| `Message`               | `brynhild.session`           | Single message          |
| `Tool`                  | `brynhild.tools.base`        | Tool ABC                |
| `ToolResult`            | `brynhild.tools.base`        | Execution result        |
| `ToolRegistry`          | `brynhild.tools.registry`    | Tool container          |
| `LLMProvider`           | `brynhild.api.base`          | Provider ABC            |
| `StreamEvent`           | `brynhild.api.types`         | Streaming event         |
| `CompletionResponse`    | `brynhild.api.types`         | Complete response       |
| `HookEvent`             | `brynhild.hooks.events`      | Event enum              |
| `HookContext`           | `brynhild.hooks.events`      | Event context           |
| `HookResult`            | `brynhild.hooks.events`      | Hook response           |
| `Plugin`                | `brynhild.plugins.manifest`  | Plugin instance         |
| `Skill`                 | `brynhild.skills.skill`      | Skill instance          |
| `ModelProfile`          | `brynhild.profiles.types`    | Profile config          |
| `ConversationProcessor` | `brynhild.core.conversation` | Main loop               |
| `ConversationCallbacks` | `brynhild.core.conversation` | UI interface            |
| `ContextBuilder`        | `brynhild.core.context`      | Prompt builder          |

### Test Organization

```
tests/
├── api/           # Provider tests
├── cli/           # CLI command tests
├── config/        # Settings tests
├── core/          # Conversation & context tests
├── e2e/           # End-to-end scenarios
├── hooks/         # Hook system tests
├── integration/   # Cross-module integration
├── live/          # Real API tests (requires keys)
├── plugins/       # Plugin system tests
├── profiles/      # Profile system tests
├── session/       # Session management tests
├── skills/        # Skill system tests
├── system/        # System-level tests
├── tools/         # Tool tests
└── ui/            # UI component tests
```

---

## Version History

| Version | Date    | Changes                            |
|---------|---------|------------------------------------|
| 0.1.0   | 2024-12 | Initial architecture documentation |

