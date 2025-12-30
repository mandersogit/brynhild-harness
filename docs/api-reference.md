# Brynhild API Reference

> **Version**: 0.1.0  
> **Last Updated**: 2024-12-03

This document provides a comprehensive API reference for Brynhild, covering all public modules, classes, and functions.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Module Overview](#module-overview)
3. [Core Modules](#core-modules)
   - [brynhild.config](#brynhildconfig)
   - [brynhild.api](#brynhildapi)
   - [brynhild.core](#brynhildcore)
   - [brynhild.tools](#brynhildtools)
4. [Extension Modules](#extension-modules)
   - [brynhild.hooks](#brynhildhooks)
   - [brynhild.session](#brynhildsession)
   - [brynhild.skills](#brynhildskills)
   - [brynhild.plugins](#brynhildplugins)
   - [brynhild.profiles](#brynhildprofiles)
5. [Utility Modules](#utility-modules)
   - [brynhild.logging](#brynhildlogging)
   - [brynhild.ui](#brynhildui)
6. [Type Reference](#type-reference)

---

## Quick Start

```python
import brynhild
import brynhild.api as api
import brynhild.tools as tools

# Load configuration from environment
settings = brynhild.Settings()

# Create a provider
provider = api.create_provider(
    provider=settings.provider,
    model=settings.model,
    api_key=settings.get_api_key(),
)

# Get the tool registry
registry = tools.get_default_registry()

# Make a completion
response = await provider.complete(
    messages=[{"role": "user", "content": "Hello!"}],
    system="You are a helpful assistant.",
)
print(response.content)
```

---

## Module Overview

| Module              | Purpose                                     | Key Exports                                  |
|---------------------|---------------------------------------------|----------------------------------------------|
| `brynhild`          | Package root                                | `Settings`, `Session`, `SessionManager`      |
| `brynhild.api`      | LLM provider interface                      | `LLMProvider`, `create_provider`, types      |
| `brynhild.config`   | Configuration management                    | `Settings`, `find_project_root`              |
| `brynhild.core`     | Conversation processing                     | `ConversationProcessor`, `ContextBuilder`    |
| `brynhild.tools`    | Tool system                                 | `Tool`, `ToolRegistry`, `ToolResult`         |
| `brynhild.hooks`    | Event hooks                                 | `HookManager`, `HookEvent`, `HookContext`    |
| `brynhild.session`  | Session persistence                         | `Session`, `SessionManager`, `Message`       |
| `brynhild.skills`   | Skill system                                | `Skill`, `SkillRegistry`                     |
| `brynhild.plugins`  | Plugin system                               | `Plugin`, `PluginRegistry`                   |
| `brynhild.profiles` | Model profiles                              | `ModelProfile`, `ProfileManager`             |
| `brynhild.logging`  | Conversation logging                        | `ConversationLogger`                         |
| `brynhild.ui`       | User interface                              | `BrynhildApp`, renderers                     |

---

## Core Modules

### brynhild.config

Configuration management using pydantic-settings.

#### Settings

```python
class Settings(pydantic_settings.BaseSettings)
```

Layered configuration from YAML files and environment variables. Use double underscores (`__`) for nested paths.

**Config File:** `~/.config/brynhild/config.yaml`

**Key Settings:**

| Setting Path | Type | Default | Env Var |
|-------------|------|---------|---------|
| `providers.default` | `str` | `"openrouter"` | `BRYNHILD_PROVIDERS__DEFAULT` |
| `models.default` | `str` | `"openai/gpt-oss-120b"` | `BRYNHILD_MODELS__DEFAULT` |
| `behavior.max_tokens` | `int` | `8192` | `BRYNHILD_BEHAVIOR__MAX_TOKENS` |
| `behavior.verbose` | `bool` | `False` | `BRYNHILD_BEHAVIOR__VERBOSE` |
| `sandbox.enabled` | `bool` | `True` | `BRYNHILD_SANDBOX__ENABLED` |
| `sandbox.allow_network` | `bool` | `False` | `BRYNHILD_SANDBOX__ALLOW_NETWORK` |
| `logging.enabled` | `bool` | `True` | `BRYNHILD_LOGGING__ENABLED` |

**API Key:** `OPENROUTER_API_KEY` (unchanged)

See `brynhild config show` to inspect effective configuration.
| `disable_builtin_tools`        | `bool`         | `False`                 | `BRYNHILD_DISABLE_BUILTIN_TOOLS`      |
| `disabled_tools`               | `str`          | `""`                    | `BRYNHILD_DISABLED_TOOLS`             |
| `reasoning_format`             | `str`          | `"auto"`                | `BRYNHILD_REASONING_FORMAT`           |

**Properties:**

| Property       | Type   | Description                           |
|----------------|--------|---------------------------------------|
| `config_dir`   | `Path` | User config directory (`~/.brynhild`) |
| `project_root` | `Path` | Project root (git root or cwd)        |
| `sessions_dir` | `Path` | Session storage directory             |
| `logs_dir`     | `Path` | Conversation logs directory           |

**Methods:**

```python
def get_api_key(self) -> str | None
def get_allowed_paths(self) -> list[Path]
def get_disabled_tools(self) -> set[str]
def is_tool_disabled(self, tool_name: str) -> bool
def to_dict(self) -> dict[str, Any]

@classmethod
def construct_without_dotenv(cls, **kwargs) -> Settings
    """Create Settings without loading .env file (useful for testing)."""
```

**Example:**

```python
import brynhild.config as config

# Load from environment
settings = config.Settings()

# Override specific values
settings = config.Settings(model="anthropic/claude-3-opus")

# For testing (ignores .env file)
settings = config.Settings.construct_without_dotenv(
    provider="ollama",
    model="llama3",
)
```

#### Functions

```python
def find_project_root(
    start_path: Path | None = None,
    *,
    allow_wide_root: bool = False,
) -> Path
    """Find project root (git root, pyproject.toml location, or cwd)."""

def find_git_root(start_path: Path | None = None) -> Path | None
    """Find the git repository root."""
```

#### Exceptions

```python
class ProjectRootTooWideError(Exception)
    """Raised when project root would be ~ or /."""
```

---

### brynhild.api

LLM provider interface and types.

#### LLMProvider (ABC)

```python
class LLMProvider(abc.ABC)
```

Abstract base class for all LLM providers.

**Abstract Properties:**

| Property | Type  | Description             |
|----------|-------|-------------------------|
| `name`   | `str` | Provider name           |
| `model`  | `str` | Current model           |

**Properties:**

| Property  | Type                   | Description          |
|-----------|------------------------|----------------------|
| `profile` | `ModelProfile \| None` | Model profile if set |

**Abstract Methods:**

```python
def supports_tools(self) -> bool
    """Whether this provider/model supports tool use."""

async def complete(
    self,
    messages: list[dict[str, Any]],
    *,
    system: str | None = None,
    tools: list[Tool] | None = None,
    max_tokens: int = 8192,
    use_profile: bool = True,
) -> CompletionResponse
    """Non-streaming completion."""

def stream(
    self,
    messages: list[dict[str, Any]],
    *,
    system: str | None = None,
    tools: list[Tool] | None = None,
    max_tokens: int = 8192,
    use_profile: bool = True,
) -> AsyncIterator[StreamEvent]
    """Streaming completion (returns async generator)."""
```

**Methods:**

```python
def supports_reasoning(self) -> bool
    """Whether model supports extended thinking (default: False)."""

def apply_profile_to_system(self, system: str | None) -> str | None
    """Enhance system prompt with profile patterns."""

def apply_profile_to_max_tokens(self, max_tokens: int) -> int
    """Enforce profile's min_max_tokens constraint."""

async def test_connection(self) -> dict[str, Any]
    """Test connection and return status dict."""
```

#### Factory Functions

```python
def create_provider(
    provider: str,
    model: str,
    *,
    api_key: str | None = None,
    **kwargs: Any,
) -> LLMProvider
    """Create a provider instance."""

def get_available_providers() -> list[str]
    """Get list of available provider names."""

def get_default_provider() -> str
    """Get the default provider name."""
```

#### Types

**CompletionResponse:**

```python
@dataclass
class CompletionResponse:
    id: str                           # Response ID
    content: str                      # Response text
    stop_reason: str | None           # Why generation stopped
    usage: Usage                      # Token usage
    tool_uses: list[ToolUse] = []     # Tool calls made
    thinking: str | None = None       # Reasoning trace

    @property
    def has_tool_use(self) -> bool
```

**StreamEvent:**

```python
@dataclass
class StreamEvent:
    type: Literal[
        "message_start", "content_start", "text_delta", "thinking_delta",
        "tool_use_start", "tool_use_delta", "content_stop",
        "message_delta", "message_stop", "error"
    ]
    text: str | None = None           # For text_delta
    thinking: str | None = None       # For thinking_delta
    tool_use: ToolUse | None = None   # For tool_use_* events
    tool_input_delta: str | None = None
    usage: Usage | None = None
    error: str | None = None
    message_id: str | None = None
    stop_reason: str | None = None
```

**Usage:**

```python
@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int
```

**ToolUse:**

```python
@dataclass
class ToolUse:
    id: str                     # Unique ID for this tool call
    name: str                   # Tool name
    input: dict[str, Any]       # Tool input
```

**Tool (API definition):**

```python
@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]

    def to_anthropic_format(self) -> dict[str, Any]
    def to_openai_format(self) -> dict[str, Any]
```

---

### brynhild.core

Core conversation processing logic.

#### ConversationProcessor

```python
class ConversationProcessor
```

Unified conversation loop for streaming, tool execution, and multi-round interactions.

**Constructor:**

```python
def __init__(
    self,
    provider: LLMProvider,
    callbacks: ConversationCallbacks,
    *,
    tool_registry: ToolRegistry | None = None,
    max_tokens: int = 8192,
    max_tool_rounds: int = 10,
    auto_approve_tools: bool = False,
    dry_run: bool = False,
    logger: ConversationLogger | None = None,
    hook_manager: HookManager | None = None,
    session_id: str = "",
    cwd: Path | None = None,
) -> None
```

**Methods:**

```python
async def process_streaming(
    self,
    messages: list[dict[str, Any]],
    system_prompt: str,
) -> ConversationResult
    """Process a turn with streaming."""

async def process_complete(
    self,
    messages: list[dict[str, Any]],
    system_prompt: str,
) -> ConversationResult
    """Process a turn without streaming."""
```

#### ConversationCallbacks (ABC)

```python
class ConversationCallbacks(abc.ABC)
```

UI abstraction for conversation events.

**Required Methods:**

| Method                                           | Description                |
|--------------------------------------------------|----------------------------|
| `on_stream_start()`                              | Streaming begins           |
| `on_stream_end()`                                | Streaming ends             |
| `on_thinking_delta(text: str)`                   | Thinking token received    |
| `on_thinking_complete(full_text: str)`           | Thinking finished          |
| `on_text_delta(text: str)`                       | Response token received    |
| `on_text_complete(full_text: str, thinking: str \| None)` | Response finished |
| `on_tool_call(tool_call: ToolCallDisplay)`       | Tool about to execute      |
| `request_tool_permission(tool_call: ToolCallDisplay) -> bool` | Get permission |
| `on_tool_result(result: ToolResultDisplay)`      | Tool executed              |
| `on_round_start(round_num: int)`                 | Tool round begins          |

**Optional Methods:**

| Method                    | Default      | Description          |
|---------------------------|--------------|----------------------|
| `is_cancelled() -> bool`  | `False`      | Check for cancel     |
| `on_info(message: str)`   | No-op        | Info message         |

#### ConversationResult

```python
@dataclass
class ConversationResult:
    response_text: str              # Final response
    thinking: str | None            # Thinking trace
    tool_uses: list[ToolUse]        # Tools called
    tool_results: list[ToolResult]  # Tool outputs
    input_tokens: int               # Total input tokens
    output_tokens: int              # Total output tokens
    stop_reason: str | None         # Why stopped
    cancelled: bool = False         # User cancelled
    messages: list[dict] = []       # Updated history
```

#### ContextBuilder

```python
class ContextBuilder
```

Builds system prompt with rules, skills, and profile patterns.

**Constructor:**

```python
def __init__(
    self,
    *,
    project_root: Path | None = None,
    logger: ConversationLogger | None = None,
    include_rules: bool = True,
    include_skills: bool = True,
    profile_name: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    plugins: list[Plugin] | None = None,
) -> None
```

**Methods:**

```python
def build(self, base_system_prompt: str) -> ConversationContext
    """Build complete context with all injections."""

def get_skill_registry(self) -> SkillRegistry
    """Get skill registry for runtime triggering."""
```

#### Convenience Function

```python
def build_context(
    base_system_prompt: str,
    *,
    project_root: Path | None = None,
    logger: ConversationLogger | None = None,
    include_rules: bool = True,
    include_skills: bool = True,
    profile_name: str | None = None,
    model: str | None = None,
    provider: str | None = None,
) -> ConversationContext
```

---

### brynhild.tools

Tool system for LLM-world interaction.

#### Tool (ABC)

```python
class Tool(abc.ABC)
```

Base class for all tools.

**Required Properties (abstract):**

| Property       | Type              | Description              |
|----------------|-------------------|--------------------------|
| `name`         | `str`             | Tool identifier          |
| `description`  | `str`             | LLM-facing description   |
| `input_schema` | `dict[str, Any]`  | JSON Schema for inputs   |

**Optional Properties:**

| Property              | Type         | Default   | Description              |
|-----------------------|--------------|-----------|--------------------------|
| `version`             | `str`        | `"0.0.0"` | Tool version             |
| `categories`          | `list[str]`  | `[]`      | Category tags            |
| `examples`            | `list[dict]` | `[]`      | Usage examples           |
| `requires_permission` | `bool`       | `True`    | Needs user approval      |

**Required Method:**

```python
async def execute(self, input: dict[str, Any]) -> ToolResult
    """Execute the tool."""
```

**Helper Methods:**

```python
def to_api_format(self) -> dict[str, Any]
    """Convert to Anthropic API format."""

def to_openai_format(self) -> dict[str, Any]
    """Convert to OpenAI/OpenRouter format."""

def _require_input(
    self,
    input: dict[str, Any],
    key: str,
    *,
    label: str | None = None,
) -> str | ToolResult
    """Validate required input, return error ToolResult if missing."""
```

#### ToolResult

```python
@dataclass
class ToolResult:
    success: bool           # Whether operation succeeded
    output: str             # Output shown to LLM
    error: str | None = None  # Error message if failed

    def to_dict(self) -> dict[str, Any]
```

#### ToolRegistry

```python
class ToolRegistry
```

Registry for tool instances.

**Methods:**

| Method                             | Returns        | Description          |
|------------------------------------|----------------|----------------------|
| `register(tool: Tool)`             | `None`         | Add a tool           |
| `get(name: str)`                   | `Tool \| None` | Lookup by name       |
| `get_or_raise(name: str)`          | `Tool`         | Lookup or KeyError   |
| `list_tools()`                     | `list[Tool]`   | All tools, sorted    |
| `list_names()`                     | `list[str]`    | Tool names, sorted   |
| `to_api_format()`                  | `list[dict]`   | Anthropic format     |
| `to_openai_format()`               | `list[dict]`   | OpenAI format        |

**Factory Functions:**

```python
def get_default_registry() -> ToolRegistry
    """Get global singleton registry with builtins."""

def create_default_registry() -> ToolRegistry
    """Create new registry with builtins."""

def build_registry_from_settings(settings: Settings) -> ToolRegistry
    """Build registry from Settings (respects disabled_tools)."""
```

#### Built-in Tools

| Tool             | Name           | Permission   | Description            |
|------------------|----------------|--------------|------------------------|
| `BashTool`       | `"Bash"`       | Required     | Execute shell commands |
| `FileReadTool`   | `"Read"`       | Not required | Read files             |
| `FileWriteTool`  | `"Write"`      | Required     | Write files            |
| `FileEditTool`   | `"Edit"`       | Required     | Edit files             |
| `GrepTool`       | `"Grep"`       | Not required | Search file contents   |
| `GlobTool`       | `"Glob"`       | Not required | Find files by pattern  |
| `InspectTool`    | `"Inspect"`    | Not required | Inspect Python objects |
| `LearnSkillTool` | `"LearnSkill"` | Not required | Load skills on demand  |

#### Sandbox

```python
@dataclass
class SandboxConfig:
    project_root: Path
    allowed_paths: list[Path] = []
    allow_network: bool = False
    skip_sandbox: bool = False

def validate_path(
    path: str,
    base_dir: Path,
    config: SandboxConfig,
    operation: Literal["read", "write"],
) -> Path
    """Validate and resolve a path."""

class PathValidationError(Exception)
    """Path validation failed."""

class SandboxUnavailableError(Exception)
    """Sandbox not available on this platform."""
```

#### SandboxMixin

```python
class SandboxMixin
```

Mixin for tools needing path validation.

**Methods:**

```python
def _get_sandbox_config(self) -> SandboxConfig
def _resolve_and_validate(self, path: str, operation: Literal["read", "write"]) -> Path
def _resolve_path_or_error(self, path: str, operation: Literal["read", "write"]) -> Path | ToolResult
```

---

## Extension Modules

### brynhild.hooks

Event hook system for extensibility.

#### HookEvent (Enum)

| Event                | Can Block | Can Modify | Description               |
|----------------------|-----------|------------|---------------------------|
| `PLUGIN_INIT`        | No        | No         | Plugin initialized        |
| `PLUGIN_SHUTDOWN`    | No        | No         | Plugin shutting down      |
| `SESSION_START`      | No        | No         | Session begins            |
| `SESSION_END`        | No        | No         | Session ends              |
| `PRE_TOOL_USE`       | Yes       | Yes        | Before tool execution     |
| `POST_TOOL_USE`      | No        | Yes        | After tool execution      |
| `PRE_MESSAGE`        | Yes       | Yes        | Before sending to LLM     |
| `POST_MESSAGE`       | No        | Yes        | After LLM response        |
| `USER_PROMPT_SUBMIT` | Yes       | Yes        | User input submitted      |
| `PRE_COMPACT`        | No        | Yes        | Before context compaction |
| `ERROR`              | No        | No         | Error occurred            |

#### HookAction (Enum)

| Value      | Description                      |
|------------|----------------------------------|
| `CONTINUE` | Proceed normally                 |
| `BLOCK`    | Stop operation, show message     |
| `SKIP`     | Skip silently                    |

#### HookContext

```python
@dataclass
class HookContext:
    event: HookEvent
    session_id: str
    cwd: Path
    plugin_name: str | None = None      # Plugin events
    plugin_path: Path | None = None     # Plugin events
    tool: str | None = None             # Tool events
    tool_input: dict | None = None      # PRE_TOOL_USE
    tool_result: ToolResult | None = None  # POST_TOOL_USE
    message: str | None = None          # Message events
    response: str | None = None         # POST_MESSAGE
    error: str | None = None            # ERROR
    compaction_strategy: str | None = None  # PRE_COMPACT

    def to_dict(self) -> dict[str, Any]
    def to_json(self) -> str
    def to_env_vars(self) -> dict[str, str]
```

#### HookResult

```python
@dataclass
class HookResult:
    action: HookAction = HookAction.CONTINUE
    message: str | None = None
    modified_input: dict | None = None       # For PRE_TOOL_USE
    modified_output: str | None = None       # For POST_TOOL_USE
    modified_message: str | None = None      # For PRE_MESSAGE
    modified_response: str | None = None     # For POST_MESSAGE
    inject_system_message: str | None = None # Context injection

    @classmethod
    def construct_continue(cls) -> HookResult
    @classmethod
    def construct_block(cls, message: str) -> HookResult
    @classmethod
    def construct_skip(cls) -> HookResult
    @classmethod
    def from_dict(cls, data: dict) -> HookResult
```

#### HookManager

```python
class HookManager
```

**Class Methods:**

```python
@classmethod
def from_config(cls, project_root: Path | None = None) -> HookManager
    """Load from config files."""

@classmethod
def construct_empty(cls) -> HookManager
    """Create empty manager."""
```

**Methods:**

```python
async def dispatch(
    self,
    event: HookEvent,
    context: HookContext,
) -> HookResult
    """Dispatch event to all matching hooks."""

def get_hooks_for_event(self, event: HookEvent) -> list[HookDefinition]
def has_hooks_for_event(self, event: HookEvent) -> bool
```

#### Context Compaction

```python
class ContextCompactor:
    def __init__(
        self,
        strategy: str = "keep_recent",
        keep_count: int = 20,
        preserve_system: bool = True,
    )

    def should_compact(
        self,
        messages: list[dict],
        max_tokens: int,
        current_usage: int,
    ) -> bool

    def compact(self, messages: list[dict]) -> CompactionResult

@dataclass
class CompactionResult:
    compacted_messages: list[dict]
    removed_count: int
    strategy: str
```

#### Stuck Detection

```python
class StuckDetector:
    def __init__(self, threshold: int = 3)
    def check(self, tool_name: str, tool_input: dict) -> StuckState
    def reset(self) -> None

@dataclass
class StuckState:
    is_stuck: bool
    reason: str | None = None
    suggestion: str | None = None
```

---

### brynhild.session

Session persistence and management.

#### Message

```python
@dataclass
class Message:
    role: Literal["user", "assistant", "system", "tool_use", "tool_result"]
    content: str
    timestamp: str  # ISO format, auto-generated
    tool_name: str | None = None
    tool_input: dict | None = None
    tool_result: str | None = None

    def to_dict(self) -> dict
    @classmethod
    def from_dict(cls, data: dict) -> Message
```

#### Session

```python
@dataclass
class Session:
    id: str
    cwd: str
    created_at: str
    updated_at: str
    model: str
    provider: str
    messages: list[Message] = []
    title: str | None = None
    tool_metrics: dict | None = None

    @classmethod
    def create(
        cls,
        cwd: Path | str | None = None,
        model: str = "openai/gpt-oss-120b",
        provider: str = "openrouter",
    ) -> Session

    def add_message(
        self,
        role: Literal[...],
        content: str,
        **kwargs,
    ) -> Message

    def to_dict(self) -> dict
    def summary(self) -> dict
```

#### SessionManager

```python
class SessionManager:
    def __init__(self, sessions_dir: Path)

    def exists(self, session_id: str) -> bool
    def save(self, session: Session) -> Path
    def load(self, session_id: str) -> Session | None
    def delete(self, session_id: str) -> bool
    def rename(self, old_id: str, new_id: str) -> bool
    def list_sessions(self) -> list[Session]
    def list_summaries(self) -> list[dict]
    def get_or_create(self, session_id: str | None = None, **kwargs) -> Session
```

#### Functions

```python
def generate_session_id() -> str
    """Generate 8-char alphanumeric ID."""

def generate_session_name() -> str
    """Generate timestamped name (session-YYYYMMDD-HHMMSS)."""

def validate_session_id(session_id: str) -> str
    """Validate format, raise InvalidSessionIdError if invalid."""
```

---

### brynhild.skills

Skill system for domain-specific capabilities.

#### Skill

```python
@dataclass
class Skill:
    frontmatter: SkillFrontmatter
    body: str              # Instructions (markdown)
    path: Path             # Skill directory
    source: str = "project"  # Discovery source

    # Properties from frontmatter
    @property
    def name(self) -> str
    @property
    def description(self) -> str
    @property
    def license(self) -> str | None
    @property
    def allowed_tools(self) -> list[str]

    # Other properties
    @property
    def skill_file(self) -> Path
    @property
    def body_line_count(self) -> int
    @property
    def exceeds_soft_limit(self) -> bool  # >500 lines

    def list_reference_files(self) -> list[Path]
    def list_scripts(self) -> list[Path]
    def get_metadata_for_prompt(self) -> str
    def get_full_content(self) -> str
```

#### SkillFrontmatter

```python
class SkillFrontmatter(pydantic.BaseModel):
    name: str           # Required, pattern: ^[a-z0-9][a-z0-9-]*[a-z0-9]$
    description: str    # Required, max 1024 chars
    license: str | None = None
    allowed_tools: list[str] = []  # alias: "allowed-tools"
    metadata: dict = {}
```

#### SkillRegistry

```python
class SkillRegistry:
    def __init__(
        self,
        project_root: Path | None = None,
        plugins: list[Plugin] | None = None,
    )

    def list_skills(self) -> list[Skill]
    def get_skill(self, name: str) -> Skill | None
    def get_metadata_for_prompt(self) -> str
    def trigger_skill(self, name: str) -> str | None
```

#### Functions

```python
def load_skill(skill_dir: Path, source: str = "project") -> Skill
def parse_skill_markdown(content: str) -> tuple[SkillFrontmatter, str]

# Discovery paths
def get_global_skills_path() -> Path
def get_project_skills_path(project_root: Path) -> Path
def get_skill_search_paths(project_root: Path, plugins: list | None) -> list[Path]
```

---

### brynhild.plugins

Plugin system for extensibility.

#### PluginManifest

```python
class PluginManifest(pydantic.BaseModel):
    # Required
    name: str       # Pattern: ^[a-z0-9][a-z0-9-]*[a-z0-9]$
    version: str    # Semantic version

    # Optional
    description: str = ""
    author: str = ""
    license: str = ""
    brynhild_version: str = ">=0.1.0"

    # Component declarations
    commands: list[str] = []
    tools: list[str] = []
    hooks: bool = False
    skills: list[str] = []
    providers: list[str] = []
```

#### Plugin

```python
@dataclass
class Plugin:
    manifest: PluginManifest
    path: Path
    enabled: bool = True

    @property
    def name(self) -> str
    @property
    def version(self) -> str
    @property
    def commands_path(self) -> Path
    @property
    def tools_path(self) -> Path
    @property
    def hooks_path(self) -> Path
    @property
    def skills_path(self) -> Path
    @property
    def providers_path(self) -> Path

    def has_commands(self) -> bool
    def has_tools(self) -> bool
    def has_hooks(self) -> bool
    def has_skills(self) -> bool
    def has_providers(self) -> bool
```

#### PluginRegistry

```python
class PluginRegistry:
    def __init__(self, project_root: Path | None = None)

    def get_enabled_plugins(self) -> Iterator[Plugin]
    def get_plugin(self, name: str) -> Plugin | None
```

#### Discovery Functions

```python
def get_global_plugins_path() -> Path
def get_project_plugins_path(project_root: Path) -> Path
def get_plugin_search_paths(project_root: Path | None = None) -> list[Path]
```

#### Rules System

```python
class RulesManager:
    def __init__(self, project_root: Path | None = None)

    def get_rules_for_prompt(self) -> str
    def list_rule_files(self) -> list[dict]

# Discovery
RULE_FILES = ["AGENTS.md", ".cursorrules", "rules.md", ".brynhild/rules.md"]

def discover_rule_files(project_root: Path) -> list[Path]
def load_rule_file(path: Path) -> str
def load_global_rules() -> str
```

---

### brynhild.profiles

Model-specific configuration profiles.

#### ModelProfile

```python
@dataclass
class ModelProfile:
    # Identity
    name: str
    family: str = ""
    description: str = ""

    # API defaults
    default_temperature: float = 0.7
    default_max_tokens: int = 8192
    min_max_tokens: int | None = None
    supports_tools: bool = True
    supports_reasoning: bool = False
    supports_streaming: bool = True
    api_params: dict = {}

    # System prompt
    system_prompt_prefix: str = ""
    system_prompt_suffix: str = ""
    prompt_patterns: dict[str, str] = {}
    enabled_patterns: list[str] = []

    # Tool configuration
    tool_format: str = "openai"
    tool_parallelization: bool = True
    max_tools_per_turn: int | None = None

    # Behavioral settings
    eagerness: Literal["minimal", "low", "medium", "high"] = "medium"
    verbosity: Literal["low", "medium", "high"] = "medium"
    thoroughness: Literal["fast", "balanced", "thorough"] = "balanced"

    # Stuck detection
    stuck_detection_enabled: bool = True
    max_similar_tool_calls: int = 3

    def get_enabled_patterns_text(self) -> str
    def build_system_prompt(self, base_prompt: str) -> str
```

#### ProfileManager

```python
class ProfileManager:
    def get_profile(self, name: str) -> ModelProfile | None
    def resolve(self, model: str, provider: str | None = None) -> ModelProfile | None
    def list_profiles(self) -> list[ModelProfile]
```

---

## Utility Modules

### brynhild.logging

Conversation logging to JSONL files.

#### ConversationLogger

```python
class ConversationLogger:
    def __init__(
        self,
        *,
        log_dir: Path | str | None = None,
        log_file: Path | str | None = None,
        private_mode: bool = True,
        provider: str = "unknown",
        model: str = "unknown",
        enabled: bool = True,
    )

    # Core logging
    def log_system_prompt(self, prompt: str) -> None
    def log_user_message(self, content: str) -> None
    def log_assistant_message(self, content: str, thinking: str | None = None) -> None
    def log_thinking(self, content: str) -> None
    def log_tool_call(self, tool_name: str, tool_input: dict, tool_id: str | None = None) -> None
    def log_tool_result(
        self,
        tool_name: str,
        success: bool,
        output: str | None = None,
        error: str | None = None,
        tool_id: str | None = None,
        duration_ms: float | None = None,
    ) -> None
    def log_error(self, error: str, context: str | None = None) -> None
    def log_usage(self, input_tokens: int, output_tokens: int) -> None
    def log_tool_metrics(self, metrics: dict) -> None

    # Context logging
    def log_context_init(self, base_system_prompt: str) -> None
    def log_context_injection(
        self,
        source: str,
        location: str,
        content: str,
        *,
        origin: str | None = None,
        trigger_type: str | None = None,
        trigger_match: str | None = None,
        metadata: dict | None = None,
    ) -> None
    def log_context_ready(self, system_prompt_hash: str | None = None) -> None
    def log_skill_triggered(
        self,
        skill_name: str,
        skill_content: str,
        trigger_type: str,
        **kwargs,
    ) -> None

    # Properties
    @property
    def file_path(self) -> Path | None
    @property
    def enabled(self) -> bool
    @property
    def context_version(self) -> int

    def close(self) -> None
```

**Context Manager Support:**

```python
with ConversationLogger(log_dir="/tmp", provider="openrouter", model="gpt-4") as logger:
    logger.log_user_message("Hello")
    # ... conversation ...
# Automatically closed
```

#### LogReader

```python
class LogReader:
    def read(self, log_file: Path) -> list[dict]
    def reconstruct_context(self, events: list[dict]) -> ReconstructedContext

@dataclass
class ReconstructedContext:
    system_prompt: str
    messages: list[dict]
    injections: list[LogInjection]
```

---

### brynhild.ui

User interface components.

#### Renderers

| Class                 | Layer | Purpose                    |
|-----------------------|-------|----------------------------|
| `PlainTextRenderer`   | 1     | Strings only, testable     |
| `CaptureRenderer`     | 1     | Captures output for tests  |
| `JSONRenderer`        | 2     | Machine-readable JSON      |
| `RichConsoleRenderer` | 3     | Colors and formatting      |
| `BrynhildApp`         | 4     | Full interactive TUI       |

#### BrynhildApp

```python
def create_app(
    provider: LLMProvider,
    *,
    tool_registry: ToolRegistry | None = None,
    max_tokens: int = 8192,
    auto_approve_tools: bool = False,
    dry_run: bool = False,
    logger: ConversationLogger | None = None,
    hook_manager: HookManager | None = None,
    profile: ModelProfile | None = None,
    initial_messages: list[dict] | None = None,
    session_id: str | None = None,
    sessions_dir: Path | None = None,
) -> BrynhildApp
```

#### ConversationRunner

```python
class ConversationRunner:
    def __init__(
        self,
        provider: LLMProvider,
        renderer: Renderer,
        *,
        tool_registry: ToolRegistry | None = None,
        logger: ConversationLogger | None = None,
        hook_manager: HookManager | None = None,
        auto_approve_tools: bool = False,
        dry_run: bool = False,
    )

    async def run_single(self, message: str, system_prompt: str) -> ConversationResult
```

---

## Type Reference

### Common Type Aliases

```python
from typing import Any, Literal, AsyncIterator
from pathlib import Path

MessageRole = Literal["user", "assistant", "system", "tool_use", "tool_result"]
HookActionType = Literal["continue", "block", "skip"]
OperationType = Literal["read", "write"]
```

### Import Conventions

Brynhild follows a specific import convention:

```python
# External packages: underscore prefix
import pathlib as _pathlib
import typing as _typing
import pydantic as _pydantic

# Internal brynhild: no underscore
import brynhild.config as config
import brynhild.api as api
import brynhild.tools as tools
```

This makes it immediately clear which symbols are from external dependencies vs. internal code.

---

## See Also

- [Architecture Overview](architecture-overview.md) - High-level system design
- [Plugin Development Guide](plugin-development-guide.md) - Creating plugins
- [Plugin API Reference](plugin-api-reference.md) - Complete plugin extension API
- [Tool Testing Guide](tool-testing.md) - Testing custom tools

