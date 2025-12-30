"""
Main CLI entry point for Brynhild.

Provides the command-line interface using Click.
Supports both interactive and non-interactive (print) modes.
"""

import asyncio as _asyncio
import datetime as _datetime
import json as _json
import pathlib as _pathlib
import sys as _sys
import typing as _typing

import click as _click

import brynhild
import brynhild.api as api
import brynhild.cli.dev as cli_dev
import brynhild.config as config
import brynhild.core.conversation as core_conversation
import brynhild.logging as logging
import brynhild.session as session
import brynhild.tools as tools
import brynhild.ui as ui

# Custom Click context settings for better help formatting
CONTEXT_SETTINGS: dict[str, _typing.Any] = {
    "help_option_names": ["-h", "--help"],
    "max_content_width": 100,
}


def _run_async(coro: _typing.Coroutine[_typing.Any, _typing.Any, _typing.Any]) -> _typing.Any:
    """Run an async coroutine synchronously."""
    return _asyncio.run(coro)


def _validate_sandbox_availability(settings: config.Settings) -> None:
    """Validate sandbox is available on Linux, or skip is explicit.

    On Linux, bubblewrap is required for sandbox protection. This function
    checks that it's available and functional, failing fast with helpful
    error messages if not.

    On macOS, sandbox-exec is built-in, so no validation is needed.
    """
    import platform as _platform

    if _platform.system() != "Linux":
        return  # macOS has sandbox-exec built in, others unsupported

    if settings.dangerously_skip_sandbox:
        import warnings as _warnings

        _warnings.warn(
            "Running without sandbox protection. "
            "AI-generated commands could harm your system.",
            RuntimeWarning,
            stacklevel=2,
        )
        return

    # Check that bubblewrap is available and functional
    import brynhild.tools.sandbox_linux as sandbox_linux

    try:
        sandbox_linux.require_bwrap()
    except (sandbox_linux.BubblewrapNotFoundError, sandbox_linux.BubblewrapNotFunctionalError) as e:
        _click.echo(str(e), err=True)
        raise SystemExit(1) from None


@_click.group(invoke_without_command=True, context_settings=CONTEXT_SETTINGS)
@_click.version_option(brynhild.__version__, "-v", "--version", prog_name="brynhild")
@_click.option(
    "-p",
    "--print",
    "print_mode",
    is_flag=True,
    help="Print mode: output response and exit (non-interactive)",
)
@_click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output in JSON format (implies --print)",
)
@_click.option(
    "--provider",
    type=_click.Choice(["anthropic", "openrouter", "bedrock", "vertex"]),
    default=None,
    help="LLM provider to use",
)
@_click.option(
    "--model",
    type=str,
    default=None,
    help="Model to use for completions",
)
@_click.option(
    "--verbose",
    is_flag=True,
    help="Enable verbose output",
)
@_click.option(
    "--resume",
    type=str,
    default=None,
    help="Resume a previous session by ID",
)
@_click.option(
    "--session",
    "session_name",
    type=str,
    default=None,
    help="Session name (for saving). If not set, auto-generates timestamp name.",
)
@_click.option(
    "--profile",
    type=str,
    default=None,
    help="Model profile to use (e.g., 'gpt-oss', 'claude')",
)
@_click.option(
    "--dangerously-skip-permissions",
    is_flag=True,
    hidden=True,
    help="Skip all permission checks",
)
@_click.option(
    "--dangerously-skip-sandbox",
    is_flag=True,
    help="Skip OS-level sandbox (DANGEROUS - for testing only)",
)
@_click.option(
    "--show-thinking",
    is_flag=True,
    help="Display full thinking/reasoning content (for debugging)",
)
@_click.option(
    "--show-cost",
    is_flag=True,
    help="Display cost information in token footers (OpenRouter only)",
)
@_click.pass_context
def cli(
    ctx: _click.Context,
    print_mode: bool,
    json_output: bool,
    provider: str | None,
    model: str | None,
    verbose: bool,
    resume: str | None,
    session_name: str | None,
    profile: str | None,
    dangerously_skip_permissions: bool,
    dangerously_skip_sandbox: bool,
    show_thinking: bool,
    show_cost: bool,
) -> None:
    """
    Brynhild - AI coding assistant.

    Run without arguments for interactive mode.
    Use 'brynhild chat "prompt"' for single-query mode.

    \b
    Examples:
        brynhild                              # Interactive mode
        brynhild chat "explain this code"    # Single query
        brynhild chat -p "list files"        # Print mode (non-interactive)
        brynhild chat -f prompt.txt          # Read prompt from file
        echo "prompt" | brynhild chat -p     # Pipe input
        brynhild config                      # Show configuration
        brynhild api test                    # Test API connectivity
    """
    # Load settings from environment, then override with CLI args
    settings = config.Settings()

    if provider:
        settings.provider = provider
    if model:
        settings.model = model
    if verbose:
        settings.verbose = verbose
    if dangerously_skip_permissions:
        settings.dangerously_skip_permissions = dangerously_skip_permissions
    if dangerously_skip_sandbox:
        settings.dangerously_skip_sandbox = dangerously_skip_sandbox

    # Validate sandbox availability on Linux (fail fast)
    _validate_sandbox_availability(settings)

    # JSON implies print mode
    if json_output:
        print_mode = True
        settings.output_format = "json"

    # Create session manager
    session_manager = session.SessionManager(settings.sessions_dir)

    # Store settings in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["settings"] = settings
    ctx.obj["session_manager"] = session_manager
    ctx.obj["print_mode"] = print_mode
    ctx.obj["json_output"] = json_output
    ctx.obj["resume_session"] = resume
    ctx.obj["session_name"] = session_name
    ctx.obj["profile_name"] = profile
    ctx.obj["show_thinking"] = show_thinking
    ctx.obj["show_cost"] = show_cost

    # If a subcommand is invoked, let it handle everything
    if ctx.invoked_subcommand is not None:
        return

    # No subcommand - show help or start interactive mode
    if print_mode:
        _click.echo("Error: Use 'brynhild chat -p \"prompt\"' for print mode", err=True)
        raise SystemExit(1)
    else:
        # Interactive mode with profile and session support
        _handle_interactive_mode(
            settings,
            profile_name=profile,
            resume_session_id=resume,
            session_name=session_name,
        )


def _create_renderer(
    json_output: bool,
    no_color: bool,
    *,
    show_thinking: bool = False,
    show_cost: bool = False,
) -> ui.Renderer:
    """Create the appropriate renderer based on output mode."""
    if json_output:
        return ui.JSONRenderer(show_cost=show_cost)
    elif no_color or not _sys.stdout.isatty():
        return ui.PlainTextRenderer(show_cost=show_cost)
    else:
        return ui.RichConsoleRenderer(show_thinking=show_thinking, show_cost=show_cost)


def _resolve_log_path(
    log_file: str | None,
    log_dir: _pathlib.Path,
    pattern: str = "brynhild_*.jsonl",
    exclude_prefix: str | None = "brynhild_raw_",
    error_message: str = "No logs found",
) -> _pathlib.Path:
    """Resolve a log file path argument.

    Handles three cases:
    1. Absolute path: Use as-is
    2. Relative path or filename that exists in CWD: Use as-is
    3. Just a filename that doesn't exist in CWD: Look in log_dir

    Args:
        log_file: User-provided path (absolute, relative, or filename).
        log_dir: Default log directory for finding recent logs.
        pattern: Glob pattern for finding most recent log.
        exclude_prefix: Prefix to exclude when finding most recent.
        error_message: Custom message when no logs found.

    Returns:
        Resolved path to log file.

    Raises:
        SystemExit: If log file not found.
    """
    if log_file:
        log_path = _pathlib.Path(log_file)
        # If path exists as-is (absolute or relative to CWD), use it
        # Otherwise, if it's just a filename, look in log_dir
        if not log_path.exists() and log_path.name == log_file:
            # Just a filename, no path components - look in log_dir
            log_path = log_dir / log_file
    else:
        # Find most recent
        if exclude_prefix:
            log_files = sorted(
                [f for f in log_dir.glob(pattern) if not f.name.startswith(exclude_prefix)],
                reverse=True,
            )
        else:
            log_files = sorted(log_dir.glob(pattern), reverse=True)

        if not log_files:
            _click.echo(f"{error_message} in {log_dir}", err=True)
            raise SystemExit(1)
        log_path = log_files[0]

    if not log_path.exists():
        _click.echo(f"Log file not found: {log_path}", err=True)
        raise SystemExit(1)

    return log_path


async def _run_conversation(
    settings: config.Settings,
    prompt: str,
    *,
    json_output: bool = False,
    stream: bool = True,
    no_color: bool = False,
    auto_approve: bool = False,
    dry_run: bool = False,
    tools_enabled: bool = True,
    verbose: bool = False,
    log_enabled: bool | None = None,
    log_file: _pathlib.Path | str | None = None,
    raw_log_enabled: bool = False,
    profile_name: str | None = None,
    show_thinking: bool = False,
    show_cost: bool = False,
    require_finish: bool = False,
    prompt_sources: list[str] | None = None,
    markdown_output: _pathlib.Path | None = None,
    markdown_title: str | None = None,
) -> None:
    """Run a conversation using the ConversationRunner."""
    import brynhild.core as core

    # Create renderer
    renderer = _create_renderer(
        json_output, no_color, show_thinking=show_thinking, show_cost=show_cost
    )

    # Create provider
    try:
        provider_instance = api.create_provider(
            provider=settings.provider,
            model=settings.model,
            api_key=settings.get_api_key(),
        )
    except ValueError as e:
        renderer.show_error(str(e))
        if json_output:
            renderer.finalize()
        raise SystemExit(1) from None

    # Create tool registry if tools are enabled
    tool_registry: tools.ToolRegistry | None = None
    if tools_enabled:
        tool_registry = tools.build_registry_from_settings(settings)

    # Create conversation logger
    # Use explicit parameter if set, otherwise fall back to settings
    should_log = log_enabled if log_enabled is not None else settings.log_conversations
    conv_logger: logging.ConversationLogger | None = None
    session_id = _datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    if should_log:
        conv_logger = logging.ConversationLogger(
            log_dir=settings.logs_dir,
            log_file=log_file or settings.log_file,
            private_mode=settings.log_dir_private,
            provider=settings.provider,
            model=settings.model,
            enabled=True,
        )
        if conv_logger.file_path and verbose:
            renderer.show_info(f"Logging to: {conv_logger.file_path}")

    # Create raw payload logger if enabled
    raw_logger: logging.RawPayloadLogger | None = None
    if raw_log_enabled:
        raw_logger = logging.RawPayloadLogger(
            log_dir=settings.logs_dir,
            session_id=session_id,
            private_mode=settings.log_dir_private,
            provider=settings.provider,
            model=settings.model,
            enabled=True,
        )
        if raw_logger.file_path and verbose:
            renderer.show_info(f"Raw logging to: {raw_logger.file_path}")
        # Set raw logger on provider
        provider_instance.raw_logger = raw_logger

    # Create markdown logger if output path specified
    markdown_logger: logging.MarkdownLogger | None = None
    if markdown_output:
        markdown_logger = logging.MarkdownLogger(
            output_path=markdown_output,
            title=markdown_title,
            provider=settings.provider,
            model=settings.model,
            profile=profile_name,
            include_thinking=show_thinking,
        )
        markdown_logger.log_session_start(session_id)
        if verbose:
            renderer.show_info(f"Markdown output to: {markdown_output}")

    # Build conversation context with rules, skills, and profile
    # Pass tool_registry so prompt reflects which tools are actually available
    # Use empty registry if tools disabled (prompt will say "no tools available")
    prompt_registry = tool_registry if tool_registry is not None else tools.ToolRegistry()
    base_prompt = core.get_system_prompt(settings.model, tool_registry=prompt_registry)
    context = core.build_context(
        base_prompt,
        project_root=settings.project_root,
        logger=conv_logger,
        include_rules=True,
        include_skills=True,
        profile_name=profile_name,
        model=settings.model,
        provider=settings.provider,
    )

    # Show session banner with model/profile/session info
    renderer.show_session_banner(
        model=settings.model,
        provider=settings.provider,
        profile=context.profile.name if context.profile else None,
        session=None,  # TODO: Pass actual session name when resume is implemented
    )

    # Show prompt source if prompt includes multiple sources
    if prompt_sources:
        renderer.show_prompt_source(prompt_sources, prompt)

    if verbose and context.injections:
        renderer.show_info(f"Applied {len(context.injections)} context injection(s)")
        if context.profile:
            renderer.show_info(f"Using profile: {context.profile.name}")

    # Create recovery config from profile if available
    recovery_config: core_conversation.RecoveryConfig | None = None
    if context.profile:
        recovery_config = core_conversation.RecoveryConfig.from_profile(context.profile)

    # Create conversation runner with enhanced system prompt
    runner = ui.ConversationRunner(
        provider=provider_instance,
        renderer=renderer,
        tool_registry=tool_registry,
        skill_registry=context.skill_registry,  # For runtime skill triggering
        max_tokens=settings.max_tokens,
        auto_approve_tools=auto_approve or settings.dangerously_skip_permissions,
        dry_run=dry_run,
        verbose=verbose,
        logger=conv_logger,
        markdown_logger=markdown_logger,
        system_prompt=context.system_prompt,  # Use enhanced prompt
        recovery_config=recovery_config,
        show_thinking=show_thinking,
        require_finish=require_finish,
    )

    # Log user message to markdown logger
    if markdown_logger:
        markdown_logger.log_user_message(prompt)

    try:
        # Run conversation
        if stream and not json_output:
            result = await runner.run_streaming(prompt)
        else:
            result = await runner.run_complete(prompt)

        # Finalize output (for JSON renderer, outputs the accumulated data)
        renderer.finalize(result)

    except Exception as e:
        renderer.show_error(str(e))
        if conv_logger:
            conv_logger.log_error(str(e))
        if markdown_logger:
            markdown_logger.log_error(str(e))
        if json_output:
            renderer.finalize()
        raise SystemExit(1) from None

    finally:
        # Close loggers
        if conv_logger:
            conv_logger.close()
        if raw_logger:
            raw_logger.close()
        if markdown_logger:
            markdown_logger.close()


async def _send_message(
    settings: config.Settings,
    prompt: str,
    json_output: bool,
    stream: bool = True,
) -> None:
    """Send a message to the API and display the response (legacy, no tools)."""
    await _run_conversation(
        settings,
        prompt,
        json_output=json_output,
        stream=stream,
        tools_enabled=False,
    )


def _session_messages_to_working(
    messages: list[session.Message],
) -> list[dict[str, _typing.Any]]:
    """TEMPORARY: Convert session format to working format.

    This is a lossy conversion - tool_call_ids are lost.
    Will be replaced by brynhild.messages.converters when
    the message format refactor lands (Phase 10b).
    """
    result: list[dict[str, _typing.Any]] = []
    for msg in messages:
        if msg.role in ("user", "system"):
            result.append({"role": msg.role, "content": msg.content})
        elif msg.role == "assistant":
            result.append({"role": "assistant", "content": msg.content})
        # Skip tool_use/tool_result - imperfect but functional for resume
    return result


def _handle_interactive_mode(
    settings: config.Settings,
    profile_name: str | None = None,
    resume_session_id: str | None = None,
    session_name: str | None = None,
) -> None:
    """Handle interactive TUI mode."""
    import brynhild.core as core

    # Handle session resume
    session_manager = session.SessionManager(settings.sessions_dir)
    initial_messages: list[dict[str, _typing.Any]] = []
    resumed_session: session.Session | None = None

    if resume_session_id:
        try:
            resumed_session = session_manager.load(resume_session_id)
        except session.InvalidSessionIdError as e:
            _click.echo(f"Error: {e}", err=True)
            raise SystemExit(1) from None
        if not resumed_session:
            _click.echo(f"Session not found: {resume_session_id}", err=True)
            raise SystemExit(1)
        initial_messages = _session_messages_to_working(resumed_session.messages)
        _click.echo(f"Resuming session: {resume_session_id}", err=True)
        # Use resumed session's ID unless explicitly overridden
        if not session_name:
            session_name = resumed_session.id

    # Validate session name if provided
    if session_name:
        try:
            session.validate_session_id(session_name)
        except session.InvalidSessionIdError as e:
            _click.echo(f"Error: {e}", err=True)
            raise SystemExit(1) from None
    else:
        # Generate session name if not set
        session_name = session.generate_session_name()

    # Create provider
    try:
        provider_instance = api.create_provider(
            provider=settings.provider,
            model=settings.model,
            api_key=settings.get_api_key(),
        )
    except ValueError as e:
        _click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from None

    # Create tool registry
    tool_registry = tools.build_registry_from_settings(settings)

    # Create conversation logger
    conv_logger: logging.ConversationLogger | None = None
    if settings.log_conversations:
        conv_logger = logging.ConversationLogger(
            log_dir=settings.logs_dir,
            log_file=settings.log_file,
            private_mode=settings.log_dir_private,
            provider=settings.provider,
            model=settings.model,
            enabled=True,
        )

    # Build conversation context with rules, skills, and profile
    # Pass tool_registry so prompt reflects which tools are actually available
    # Use empty registry if tools disabled (prompt will say "no tools available")
    prompt_registry = tool_registry if tool_registry is not None else tools.ToolRegistry()
    base_prompt = core.get_system_prompt(settings.model, tool_registry=prompt_registry)
    context = core.build_context(
        base_prompt,
        project_root=settings.project_root,
        logger=conv_logger,
        include_rules=True,
        include_skills=True,
        profile_name=profile_name,
        model=settings.model,
        provider=settings.provider,
    )

    # Create recovery config from profile if available
    recovery_config: core_conversation.RecoveryConfig | None = None
    if context.profile:
        recovery_config = core_conversation.RecoveryConfig.from_profile(context.profile)

    try:
        # Create and run the TUI app with enhanced system prompt
        app = ui.create_app(
            provider=provider_instance,
            tool_registry=tool_registry,
            skill_registry=context.skill_registry,  # For runtime skill triggering
            max_tokens=settings.max_tokens,
            auto_approve_tools=settings.dangerously_skip_permissions,
            conv_logger=conv_logger,
            system_prompt=context.system_prompt,  # Use enhanced prompt
            initial_messages=initial_messages,  # Resume support
            session_id=session_name,  # Session tracking
            sessions_dir=settings.sessions_dir,  # For auto-save
            recovery_config=recovery_config,
        )

        app.run()
    finally:
        # Close the logger
        if conv_logger:
            conv_logger.close()


@cli.command()
@_click.option("-p", "--print", "print_mode", is_flag=True, help="Print mode (non-interactive)")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
@_click.option("--no-stream", is_flag=True, help="Disable streaming (get complete response)")
@_click.option("--no-color", is_flag=True, help="Disable colored output")
@_click.option("--yes", "-y", "auto_approve", is_flag=True, help="Auto-approve all tool executions")
@_click.option("--dry-run", is_flag=True, help="Show tool calls without executing")
@_click.option("--tools/--no-tools", "tools_enabled", default=True, help="Enable/disable tool use")
@_click.option("--no-log", is_flag=True, help="Disable conversation logging")
@_click.option(
    "--log-file",
    type=_click.Path(dir_okay=False, path_type=_pathlib.Path),
    default=None,
    help="Explicit log file path",
)
@_click.option("--raw-log", is_flag=True, help="Enable raw payload logging (full JSON request/response)")
@_click.option(
    "--require-finish",
    is_flag=True,
    help="Require agent to call Finish tool to complete",
)
@_click.option(
    "-f",
    "--prompt-file",
    type=_click.Path(exists=True, dir_okay=False, path_type=_pathlib.Path),
    multiple=True,
    help="Read prompt from file(s); can be specified multiple times",
)
@_click.option(
    "-o",
    "--markdown-output",
    type=_click.Path(dir_okay=False, path_type=_pathlib.Path),
    default=None,
    help="Write presentation markdown to file",
)
@_click.option(
    "--markdown-title",
    type=str,
    default=None,
    help="Title for markdown output (default: timestamp)",
)
@_click.argument("prompt", required=False, nargs=-1)
@_click.pass_context
def chat(
    ctx: _click.Context,
    print_mode: bool,
    json_output: bool,
    no_stream: bool,
    no_color: bool,
    auto_approve: bool,
    dry_run: bool,
    tools_enabled: bool,
    no_log: bool,
    log_file: _pathlib.Path | None,
    raw_log: bool,
    require_finish: bool,
    prompt_file: tuple[_pathlib.Path, ...],
    markdown_output: _pathlib.Path | None,
    markdown_title: str | None,
    prompt: tuple[str, ...],
) -> None:
    """Send a prompt to the AI (single query mode)."""
    settings: config.Settings = ctx.obj["settings"]

    # Note: print_mode is accepted but not currently used - JSON output is primary
    _ = print_mode  # Acknowledge the parameter

    # Collect all prompt sources: files, stdin, ARGV (in that order)
    # Each source is wrapped in XML tags to communicate provenance to the model
    prompt_parts: list[str] = []
    prompt_sources: list[str] = []  # For display: "file:path", "stdin", "args"

    # 1. Files (in order specified)
    for f in prompt_file:
        content = f.read_text().strip()
        if content:
            prompt_parts.append(f'<prompt_file path="{f}">\n{content}\n</prompt_file>')
            prompt_sources.append(f"file:{f}")

    # 2. Stdin (if piped)
    if not _sys.stdin.isatty():
        stdin_content = _sys.stdin.read().strip()
        if stdin_content:
            prompt_parts.append(f"<stdin>\n{stdin_content}\n</stdin>")
            prompt_sources.append("stdin")

    # 3. ARGV arguments
    if prompt:
        argv_content = " ".join(prompt)
        if argv_content.strip():
            prompt_parts.append(f"<prompt>\n{argv_content}\n</prompt>")
            prompt_sources.append("args")

    # Combine all parts
    prompt_text = "\n\n".join(prompt_parts) if prompt_parts else None

    if not prompt_text:
        if json_output:
            _click.echo(_json.dumps({"error": "No prompt provided"}, indent=2))
        else:
            _click.echo(
                'Error: No prompt provided. Usage: brynhild chat "your prompt" or brynhild chat -f prompt.txt',
                err=True,
            )
        raise SystemExit(1)

    # Get profile and display options from parent context
    profile_name: str | None = ctx.obj.get("profile_name")
    show_thinking: bool = ctx.obj.get("show_thinking", False)
    show_cost: bool = ctx.obj.get("show_cost", False)

    # Send the message using new conversation runner
    _run_async(
        _run_conversation(
            settings,
            prompt_text,
            json_output=json_output,
            stream=not no_stream,
            no_color=no_color,
            auto_approve=auto_approve,
            dry_run=dry_run,
            tools_enabled=tools_enabled,
            verbose=settings.verbose,
            log_enabled=not no_log if no_log else None,
            log_file=log_file,
            raw_log_enabled=raw_log or settings.raw_log,
            profile_name=profile_name,
            show_thinking=show_thinking,
            show_cost=show_cost,
            require_finish=require_finish,
            prompt_sources=prompt_sources,
            markdown_output=markdown_output,
            markdown_title=markdown_title,
        )
    )


@cli.group(invoke_without_command=True)
@_click.pass_context
def config_cmd(ctx: _click.Context) -> None:
    """Configuration management commands.

    Without a subcommand, shows configuration overview.
    """
    if ctx.invoked_subcommand is None:
        # Default behavior: show overview (backward compatible)
        settings: config.Settings = ctx.obj["settings"]
        _click.echo("Brynhild Configuration:")
        _click.echo(f"  Provider: {settings.provider}")
        _click.echo(f"  Model: {settings.model}")
        _click.echo(f"  Max Tokens: {settings.max_tokens}")
        _click.echo(f"  API Key: {'✓ configured' if settings.get_api_key() else '✗ missing'}")
        _click.echo(f"  Project Root: {settings.project_root}")
        _click.echo(f"  Config Dir: {settings.config_dir}")
        _click.echo(f"  Sessions Dir: {settings.sessions_dir}")
        _click.echo("\nRun 'brynhild config show' for full configuration details.")


# Register config_cmd with the name "config" to avoid shadowing the module
cli.add_command(config_cmd, name="config")


@config_cmd.command(name="show")
@_click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@_click.option("--provenance", is_flag=True, help="Show where each value came from")
@_click.option("--section", type=str, default=None, help="Show specific section only")
@_click.option(
    "--color/--no-color",
    "use_color",
    default=None,
    help="Enable/disable syntax highlighting (default: auto-detect TTY)",
)
@_click.pass_context
def config_show(
    ctx: _click.Context,
    as_json: bool,
    provenance: bool,
    section: str | None,
    use_color: bool | None,
) -> None:
    """Show effective configuration from all sources.

    Displays the merged configuration from built-in defaults, user config,
    and project config. Use --provenance to see which file each value came from.

    Color output is enabled by default when outputting to a terminal.
    Override with --color/--no-color, NO_COLOR env var, or
    BRYNHILD_CONFIG_SHOW_COLOR=0|1 env var.

    Examples:
        brynhild config show              # Show all config as YAML (colorized)
        brynhild config show --json       # Show as JSON
        brynhild config show --provenance # Show config with sources
        brynhild config show --no-color   # Disable syntax highlighting
        brynhild config show | less -R    # Pipe with color (use --color)
    """
    import yaml as _yaml

    settings: config.Settings = ctx.obj["settings"]

    # Determine color mode
    color_enabled, force_color = _should_use_color(use_color)

    # Get the full config dict
    full_config = settings.model_dump(mode="json")

    # Filter to section if requested
    if section:
        if section not in full_config:
            raise _click.ClickException(f"Unknown section: {section}")
        full_config = {section: full_config[section]}

    if as_json:
        _click.echo(_json.dumps(full_config, indent=2))
    elif provenance:
        _print_config_with_provenance(full_config, color=color_enabled, force_color=force_color)
    else:
        # Pretty YAML output
        yaml_text = _yaml.dump(full_config, default_flow_style=False, sort_keys=False)
        _print_yaml(yaml_text, color=color_enabled, force_color=force_color)


def _should_use_color(cli_flag: bool | None) -> tuple[bool, bool]:
    """Determine whether to use color output.

    Priority:
    1. CLI flag (--color / --no-color) if specified
    2. BRYNHILD_CONFIG_SHOW_COLOR env var (1=on, 0=off)
    3. NO_COLOR env var (if set, disable color) - standard convention
    4. Auto-detect: color if stdout is a TTY

    Args:
        cli_flag: True for --color, False for --no-color, None for auto

    Returns:
        Tuple of (color_enabled, force_color).
        force_color is True when color was explicitly requested (not auto-detected).
    """
    import os as _os_local
    import sys as _sys_local

    # CLI flag takes highest priority
    if cli_flag is not None:
        # Explicitly requested - force it even when piping
        return (cli_flag, cli_flag)

    # Check BRYNHILD_CONFIG_SHOW_COLOR env var
    env_color = _os_local.environ.get("BRYNHILD_CONFIG_SHOW_COLOR")
    if env_color is not None:
        enabled = env_color.lower() in ("1", "true", "yes", "on")
        # Env var is explicit - force it
        return (enabled, enabled)

    # Check NO_COLOR standard (https://no-color.org/)
    if _os_local.environ.get("NO_COLOR") is not None:
        return (False, False)

    # Auto-detect: color if stdout is a TTY (don't force)
    return (_sys_local.stdout.isatty(), False)


def _print_yaml(yaml_text: str, *, color: bool = True, force_color: bool = False) -> None:
    """Print YAML text, optionally with syntax highlighting.

    Args:
        yaml_text: The YAML text to print
        color: Whether to use syntax highlighting
        force_color: Force color even when not a TTY (for piping with --color)
    """
    if color:
        try:
            import rich.console as _rich_console
            import rich.syntax as _rich_syntax

            # When forcing color (explicit --color flag):
            # - force_terminal=True: output color even when piped
            # - no_color=False: override NO_COLOR env var
            # - color_system='truecolor': override FORCE_COLOR=0 env var
            console = _rich_console.Console(
                force_terminal=force_color,
                no_color=False if force_color else None,
                color_system="truecolor" if force_color else "auto",
            )
            syntax = _rich_syntax.Syntax(
                yaml_text,
                "yaml",
                theme="monokai",
                background_color="default",
            )
            console.print(syntax)
            return
        except ImportError:
            pass  # Fall back to plain output

    _click.echo(yaml_text)


def _print_config_with_provenance(
    config_data: dict[str, _typing.Any],
    *,
    color: bool = True,
    force_color: bool = False,
) -> None:
    """Print config with provenance information (where each value came from).

    Args:
        config_data: The config dict to print.
        color: Whether to use syntax highlighting.
        force_color: Force color even when not a TTY (for piping with --color).
    """
    import brynhild.config.sources as config_sources

    # Create a fresh DCM source to query provenance
    project_root = config.find_git_root()
    source = config_sources.DeepChainMapSettingsSource(
        config.Settings,
        project_root,
    )

    # Build layer codes and legend from loaded layers
    # Codes are up to 8 chars for readability
    loaded_layers = source.get_loaded_layers()
    layer_codes: dict[int, str] = {-1: "runtime"}
    layer_paths: dict[int, _pathlib.Path] = {}  # For line number lookups
    legend_lines: list[str] = []

    # Assign readable codes (up to 8 chars)
    code_map = {"built-in": "builtin", "user": "user", "project": "project"}
    for i, (name, path) in enumerate(loaded_layers):
        code = code_map.get(name, name[:8])
        layer_codes[i] = code
        layer_paths[i] = path
        legend_lines.append(f"# [{code}] {path}")

    # Special codes for non-DCM sources
    env_code = "env"  # Environment variables
    auto_code = "auto"  # Automatic values (Pydantic defaults, computed fields)

    # Get line registries for line number lookups
    line_registries = source.get_line_registries()

    def get_line_suffix(layer_idx: int, key_path: tuple[str, ...]) -> str:
        """Get line number suffix for a key, if available."""
        if layer_idx < 0:  # runtime/front_layer has no line numbers
            return ""
        path = layer_paths.get(layer_idx)
        if path is None:
            return ""
        registry = line_registries.get(path)
        if registry is None:
            return ""
        line_info = registry.get(key_path)
        if line_info is None:
            return ""
        line, _col = line_info
        return f":{line}"

    # Collect all lines first to calculate alignment column
    lines: list[tuple[str, str]] = []  # (content, provenance_code_with_line)

    # Default layer is the last one (lowest priority = built-in)
    default_layer_idx = len(loaded_layers) - 1 if loaded_layers else 0
    builtin_code = layer_codes.get(default_layer_idx, "builtin")

    def get_prov_code_with_line(
        prov: dict[str, _typing.Any],
        key: str,
        key_path: tuple[str, ...],
    ) -> str:
        """Get the layer code with line number for a specific key.

        If the key doesn't exist in provenance, it's a Pydantic default.
        """
        if key in prov:
            layer_idx = prov[key]
            if isinstance(layer_idx, int):
                code = layer_codes.get(layer_idx, builtin_code)
                line_suffix = get_line_suffix(layer_idx, key_path)
                return f"{code}{line_suffix}"
            # Nested dict means it's a merged section
            return "merged"
        # Not in provenance = Pydantic default
        return auto_code

    def collect_lines(
        data: dict[str, _typing.Any],
        prov: dict[str, _typing.Any],
        depth: int = 0,
        path_prefix: tuple[str, ...] = (),
    ) -> None:
        """Recursively collect lines with provenance codes and line numbers."""
        indent = "  " * depth
        for key, value in data.items():
            key_path = path_prefix + (key,)
            if isinstance(value, dict):
                # Dict - check provenance structure
                dict_prov = prov.get(key)
                if isinstance(dict_prov, dict):
                    # Has per-key provenance (merged or tracked nested dict)
                    # Check if all immediate children have same source
                    child_sources = {v for v in dict_prov.values() if isinstance(v, int)}
                    if len(child_sources) == 1:
                        # All from same layer - show that layer
                        layer_idx = next(iter(child_sources))
                        code = layer_codes.get(layer_idx, builtin_code)
                        line_suffix = get_line_suffix(layer_idx, key_path)
                        prov_label = f"{code}{line_suffix}"
                    else:
                        # Mixed sources or nested dicts - show merged
                        prov_label = "merged"
                    if not value:
                        lines.append((f"{indent}{key}: {{}}", prov_label))
                    else:
                        lines.append((f"{indent}{key}:", prov_label))
                        collect_lines(value, dict_prov, depth + 1, key_path)
                elif isinstance(dict_prov, int):
                    # Whole dict from one layer (not merged)
                    code = layer_codes.get(dict_prov, builtin_code)
                    line_suffix = get_line_suffix(dict_prov, key_path)
                    prov_label = f"{code}{line_suffix}"
                    if not value:
                        lines.append((f"{indent}{key}: {{}}", prov_label))
                    else:
                        lines.append((f"{indent}{key}:", prov_label))
                        # Create provenance for children - all from same layer
                        child_prov = dict.fromkeys(value, dict_prov)
                        collect_lines(value, child_prov, depth + 1, key_path)
                else:
                    # Not in provenance = Pydantic default
                    if not value:
                        lines.append((f"{indent}{key}: {{}}", auto_code))
                    else:
                        lines.append((f"{indent}{key}:", auto_code))
                        collect_lines(value, {}, depth + 1, key_path)
            elif isinstance(value, list):
                # List - show the list marker with provenance, items inherit
                prov_code = get_prov_code_with_line(prov, key, key_path)
                if not value:
                    # Empty list - render inline
                    lines.append((f"{indent}{key}: []", prov_code))
                else:
                    lines.append((f"{indent}{key}:", prov_code))
                    for item in value:
                        if isinstance(item, str):
                            lines.append((f"{indent}  - \"{item}\"", prov_code))
                        elif item is None:
                            lines.append((f"{indent}  - null", prov_code))
                        else:
                            lines.append((f"{indent}  - {item}", prov_code))
            else:
                # Scalar value
                if isinstance(value, str):
                    formatted = f'"{value}"'
                elif value is None:
                    formatted = "null"
                else:
                    formatted = str(value)
                prov_code = get_prov_code_with_line(prov, key, key_path)
                lines.append((f"{indent}{key}: {formatted}", prov_code))

    # Collect lines for each top-level key
    dcm = source.dcm
    for key in config_data:
        key_path = (key,)
        if key not in dcm:
            # Key not in DCM - from env vars or pydantic defaults
            # Use "env" for keys that look like they came from environment
            is_env_key = key.startswith("brynhild_") or key.endswith("_api_key")
            fallback = env_code if is_env_key else auto_code

            if isinstance(config_data[key], dict):
                lines.append((f"{key}:", fallback))
                collect_lines(config_data[key], {}, depth=1, path_prefix=key_path)
            else:
                val = config_data[key]
                if isinstance(val, str):
                    lines.append((f"{key}: \"{val}\"", fallback))
                elif val is None:
                    lines.append((f"{key}: null", fallback))
                else:
                    lines.append((f"{key}: {val}", fallback))
            continue

        try:
            _, prov = dcm.get_with_provenance(key)
            if isinstance(config_data[key], dict):
                # Check provenance structure for top-level label
                if "." in prov:
                    # Scalar-like provenance
                    layer_idx = prov["."]
                    top_code = layer_codes.get(layer_idx, builtin_code)
                    line_suffix = get_line_suffix(layer_idx, key_path)
                    top_code_with_line = f"{top_code}{line_suffix}"
                elif prov:
                    # Has per-key provenance - check if all from same layer
                    child_sources = {v for v in prov.values() if isinstance(v, int)}
                    if len(child_sources) == 1:
                        layer_idx = next(iter(child_sources))
                        top_code = layer_codes.get(layer_idx, builtin_code)
                        line_suffix = get_line_suffix(layer_idx, key_path)
                        top_code_with_line = f"{top_code}{line_suffix}"
                    else:
                        top_code_with_line = "merged"
                else:
                    top_code_with_line = auto_code
                lines.append((f"{key}:", top_code_with_line))
                collect_lines(config_data[key], prov, depth=1, path_prefix=key_path)
            else:
                # Top-level scalar
                val = config_data[key]
                layer_idx = prov.get(".", default_layer_idx)
                code = layer_codes.get(layer_idx, builtin_code)
                line_suffix = get_line_suffix(layer_idx, key_path)
                code_with_line = f"{code}{line_suffix}"
                if isinstance(val, str):
                    lines.append((f"{key}: \"{val}\"", code_with_line))
                elif val is None:
                    lines.append((f"{key}: null", code_with_line))
                else:
                    lines.append((f"{key}: {val}", code_with_line))
        except (KeyError, RuntimeError):
            lines.append((f"{key}:", auto_code))
            if isinstance(config_data[key], dict):
                collect_lines(
                    config_data[key], {}, depth=1, path_prefix=key_path
                )

    # Calculate alignment column
    # Reserve space for " # [nickname]" suffix (~15 chars)
    # Default based on terminal width, or env var override
    import os as _os_local
    import shutil as _shutil
    import sys as _sys_local

    env_width = _os_local.environ.get("BRYNHILD_CONFIG_SHOW_WIDTH")
    if env_width:
        try:
            align_cap = int(env_width)
        except ValueError:
            align_cap = 70  # Fallback if invalid
    else:
        # Detect terminal width
        # When piping (e.g., to less), stdout is not a TTY but stderr usually is
        # Try stderr first, then stdout, then fallback
        term_width = 100  # Default fallback
        try:
            if _sys_local.stderr.isatty():
                # stderr is still connected to terminal (common when piping)
                term_width = _os_local.get_terminal_size(_sys_local.stderr.fileno()).columns
            elif _sys_local.stdout.isatty():
                term_width = _shutil.get_terminal_size().columns
        except (AttributeError, ValueError, OSError):
            pass  # Use fallback

        # Reserve ~15 chars for " # [nickname]" suffix
        align_cap = max(50, term_width - 15)

    max_width = max(len(content) for content, _ in lines) if lines else 0
    align_col = min(max_width + 2, align_cap)

    # Build output text
    output_lines: list[str] = []

    # Legend
    output_lines.append("# Configuration with provenance")
    output_lines.append("#")
    output_lines.append("# Sources:")
    output_lines.extend(legend_lines)
    output_lines.append(f"# [{env_code}] environment variables")
    output_lines.append(f"# [{auto_code}] automatic (code defaults, computed values)")
    output_lines.append("# [merged] values from multiple sources")
    output_lines.append("#")
    output_lines.append("")

    # Config lines with aligned provenance
    for content, code in lines:
        padding = " " * max(1, align_col - len(content))
        output_lines.append(f"{content}{padding}# [{code}]")

    # Print with optional color
    output_text = "\n".join(output_lines)
    _print_yaml(output_text, color=color, force_color=force_color)


@config_cmd.command(name="path")
@_click.option("--all", "show_all", is_flag=True, help="Show all paths even if not found")
def config_path(show_all: bool) -> None:
    """Show configuration file paths and their status.

    Lists all configuration file locations and whether they exist.

    Examples:
        brynhild config path        # Show existing config files
        brynhild config path --all  # Show all possible paths
    """
    import brynhild.config.sources as config_sources

    paths = [
        ("Built-in defaults", config_sources.get_builtin_defaults_path()),
        ("User config", config_sources.get_user_config_path()),
    ]

    # Add project config if we can detect a project root
    project_root = config.find_git_root()
    if project_root:
        paths.append(
            ("Project config", config_sources.get_project_config_path(project_root))
        )

    for name, path in paths:
        exists = path.exists()
        if exists or show_all:
            status = "✓" if exists else "✗"
            _click.echo(f"{status} {name}: {path}")


@cli.group()
def api_cmd() -> None:
    """API-related commands."""
    pass


# Register api_cmd with the name "api" to avoid shadowing the module
cli.add_command(api_cmd, name="api")


@api_cmd.command(name="providers")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
def api_providers(json_output: bool) -> None:
    """List available LLM providers."""
    providers = api.get_available_providers()

    if json_output:
        _click.echo(_json.dumps(providers, indent=2))
    else:
        _click.echo("Available Providers:")
        for p in providers:
            status = "✓" if p["key_configured"] else "✗"
            available = "" if p["available"] else " (not implemented)"
            _click.echo(f"  {status} {p['name']}: {p['description']}{available}")
            _click.echo(f"      Key: {p['key_env_var']}")
            _click.echo(f"      Default model: {p['default_model']}")


@api_cmd.command(name="test")
@_click.option("--provider", type=str, default=None, help="Provider to test")
@_click.option("--model", type=str, default=None, help="Model to test")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
@_click.option("--live", is_flag=True, help="Actually call the API (requires API key)")
@_click.pass_context
def api_test(
    ctx: _click.Context,
    provider: str | None,
    model: str | None,
    json_output: bool,
    live: bool,
) -> None:
    """Test API connectivity."""
    settings: config.Settings = ctx.obj["settings"]

    if provider:
        settings.provider = provider
    if model:
        settings.model = model

    api_key = settings.get_api_key()

    # Basic info
    result = {
        "provider": settings.provider,
        "model": settings.model,
        "api_key_configured": api_key is not None,
        "status": "ready" if api_key else "missing_api_key",
    }

    # If --live flag and API key is configured, actually test the connection
    if live and api_key:
        try:
            provider_instance = api.create_provider(
                provider=settings.provider,
                model=settings.model,
                api_key=api_key,
            )
            test_result = _run_async(provider_instance.test_connection())
            result.update(test_result)
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)

    if json_output:
        _click.echo(_json.dumps(result, indent=2))
    else:
        _click.echo(f"Provider: {result['provider']}")
        _click.echo(f"Model: {result['model']}")
        _click.echo(f"API Key: {'✓ configured' if result['api_key_configured'] else '✗ missing'}")
        _click.echo(f"Status: {result['status']}")
        if "latency_ms" in result:
            _click.echo(f"Latency: {result['latency_ms']}ms")
        if "error" in result:
            _click.echo(f"Error: {result['error']}")


@cli.group()
def session_cmd() -> None:
    """Session management commands."""
    pass


# Register session_cmd with the name "session" to avoid shadowing the module
cli.add_command(session_cmd, name="session")


@session_cmd.command(name="list")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
@_click.option("--limit", type=int, default=10, help="Maximum sessions to list")
@_click.pass_context
def session_list(ctx: _click.Context, json_output: bool, limit: int) -> None:
    """List recent sessions."""
    session_manager: session.SessionManager = ctx.obj["session_manager"]

    summaries = session_manager.list_summaries()[:limit]

    if json_output:
        _click.echo(_json.dumps(summaries, indent=2))
    else:
        if not summaries:
            _click.echo("No sessions found.")
            return

        _click.echo("Recent Sessions:")
        for s in summaries:
            title = s.get("title") or "(untitled)"
            _click.echo(
                f"  {s['id']}  {s['updated_at'][:19]}  {s['message_count']:>3} msgs  {title}"
            )


@session_cmd.command(name="show")
@_click.argument("session_id")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
@_click.pass_context
def session_show(ctx: _click.Context, session_id: str, json_output: bool) -> None:
    """Show session details."""
    session_manager: session.SessionManager = ctx.obj["session_manager"]

    try:
        sess = session_manager.load(session_id)
    except session.InvalidSessionIdError as e:
        if json_output:
            _click.echo(_json.dumps({"error": str(e)}, indent=2))
        else:
            _click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from None

    if not sess:
        if json_output:
            _click.echo(_json.dumps({"error": f"Session not found: {session_id}"}, indent=2))
        else:
            _click.echo(f"Error: Session not found: {session_id}", err=True)
        raise SystemExit(1)

    if json_output:
        _click.echo(_json.dumps(sess.to_dict(), indent=2))
    else:
        _click.echo(f"Session: {sess.id}")
        _click.echo(f"  Title: {sess.title or '(untitled)'}")
        _click.echo(f"  Created: {sess.created_at}")
        _click.echo(f"  Updated: {sess.updated_at}")
        _click.echo(f"  Model: {sess.provider}/{sess.model}")
        _click.echo(f"  Working Dir: {sess.cwd}")
        _click.echo(f"  Messages: {len(sess.messages)}")

        if sess.messages:
            _click.echo("\nRecent Messages:")
            for msg in sess.messages[-5:]:
                content_preview = msg.content[:60] + "..." if len(msg.content) > 60 else msg.content
                _click.echo(f"  [{msg.role}] {content_preview}")


@session_cmd.command(name="delete")
@_click.argument("session_id")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
@_click.option("--yes", is_flag=True, help="Skip confirmation")
@_click.pass_context
def session_delete(ctx: _click.Context, session_id: str, json_output: bool, yes: bool) -> None:
    """Delete a session."""
    session_manager: session.SessionManager = ctx.obj["session_manager"]

    try:
        sess = session_manager.load(session_id)
    except session.InvalidSessionIdError as e:
        if json_output:
            _click.echo(_json.dumps({"error": str(e)}, indent=2))
        else:
            _click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from None

    if not sess:
        if json_output:
            _click.echo(_json.dumps({"error": f"Session not found: {session_id}"}, indent=2))
        else:
            _click.echo(f"Error: Session not found: {session_id}", err=True)
        raise SystemExit(1)

    if not yes and not json_output and not _click.confirm(f"Delete session {session_id}?"):
        _click.echo("Cancelled.")
        return

    deleted = session_manager.delete(session_id)

    if json_output:
        _click.echo(_json.dumps({"deleted": deleted, "session_id": session_id}, indent=2))
    else:
        _click.echo(f"Deleted session: {session_id}")


@session_cmd.command(name="rename")
@_click.argument("old_name")
@_click.argument("new_name")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
@_click.pass_context
def session_rename(
    ctx: _click.Context, old_name: str, new_name: str, json_output: bool
) -> None:
    """Rename a session."""
    session_manager: session.SessionManager = ctx.obj["session_manager"]

    try:
        session_manager.rename(old_name, new_name)
    except session.InvalidSessionIdError as e:
        if json_output:
            _click.echo(_json.dumps({"error": str(e)}, indent=2))
        else:
            _click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from None
    except FileNotFoundError as e:
        if json_output:
            _click.echo(_json.dumps({"error": str(e)}, indent=2))
        else:
            _click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from None
    except FileExistsError as e:
        if json_output:
            _click.echo(_json.dumps({"error": str(e)}, indent=2))
        else:
            _click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from None

    if json_output:
        _click.echo(
            _json.dumps({"renamed": True, "old_name": old_name, "new_name": new_name}, indent=2)
        )
    else:
        _click.echo(f"Renamed: {old_name} → {new_name}")


# ============================================================================
# Tools Commands
# ============================================================================


@cli.group()
def tools_cmd() -> None:
    """Tool management and execution commands."""
    pass


# Register tools_cmd with the name "tools" to avoid shadowing the module
cli.add_command(tools_cmd, name="tools")


def _get_tool_registry() -> tools.ToolRegistry:
    """Get a tool registry configured from current settings."""
    settings = config.Settings()
    return tools.build_registry_from_settings(settings)


@tools_cmd.command(name="list")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
@_click.option("-v", "--verbose", is_flag=True, help="Show version and categories")
def tools_list(json_output: bool, verbose: bool) -> None:
    """List all available tools."""
    registry = _get_tool_registry()

    if json_output:
        tool_list = [
            {
                "name": t.name,
                "description": t.description,
                "version": t.version,
                "categories": t.categories,
                "requires_permission": t.requires_permission,
            }
            for t in registry.list_tools()
        ]
        _click.echo(_json.dumps(tool_list, indent=2))
    else:
        _click.echo("Available Tools:")
        for t in registry.list_tools():
            if verbose:
                version_str = f" v{t.version}" if t.version != "0.0.0" else ""
                categories_str = f" [{', '.join(t.categories)}]" if t.categories else ""
                perm_str = " [requires permission]" if t.requires_permission else ""
                _click.echo(f"  {t.name}{version_str}{categories_str}{perm_str}")
                _click.echo(f"    {t.description[:70]}...")
            else:
                _click.echo(f"  {t.name}: {t.description[:60]}...")


@tools_cmd.command(name="schema")
@_click.argument("tool_name")
def tools_schema(tool_name: str) -> None:
    """Show the input schema for a tool (always JSON)."""
    registry = _get_tool_registry()

    try:
        tool = registry.get_or_raise(tool_name)
    except KeyError as e:
        _click.echo(_json.dumps({"error": str(e)}, indent=2))
        raise SystemExit(1) from None

    schema = {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
    }

    _click.echo(_json.dumps(schema, indent=2))


@tools_cmd.command(name="exec")
@_click.argument("tool_name")
@_click.option("--input", "input_json", required=True, help="Tool input as JSON string")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
def tools_exec(
    tool_name: str,
    input_json: str,
    json_output: bool,
) -> None:
    """Execute a tool directly (for testing)."""
    registry = _get_tool_registry()

    try:
        tool = registry.get_or_raise(tool_name)
    except KeyError as e:
        if json_output:
            _click.echo(_json.dumps({"error": str(e)}, indent=2))
        else:
            _click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from None

    try:
        tool_input = _json.loads(input_json)
    except _json.JSONDecodeError as e:
        if json_output:
            _click.echo(_json.dumps({"error": f"Invalid JSON: {e}"}, indent=2))
        else:
            _click.echo(f"Error: Invalid JSON input: {e}", err=True)
        raise SystemExit(1) from None

    # Execute the tool
    result = _run_async(tool.execute(tool_input))

    if json_output:
        _click.echo(_json.dumps(result.to_dict(), indent=2))
    else:
        if result.success:
            _click.echo(result.output)
        else:
            _click.echo(f"Error: {result.error}", err=True)
            raise SystemExit(1)


@tools_cmd.command(name="stats")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
@_click.option("--log", "log_file", type=_click.Path(exists=True), help="Read stats from specific log file")
@_click.option("--session", "session_id", help="Read stats from specific session")
def tools_stats(
    json_output: bool,
    log_file: str | None,
    session_id: str | None,
) -> None:
    """Show tool usage statistics from logs or sessions."""
    import brynhild.tools.base as tools_base

    metrics: dict[str, dict[str, _typing.Any]] = {}

    if session_id:
        # Load from session
        settings = config.Settings()
        import brynhild.session as session_mod

        manager = session_mod.SessionManager(settings.sessions_dir)
        sess = manager.load(session_id)
        if not sess:
            _click.echo(f"Session not found: {session_id}", err=True)
            raise SystemExit(1)
        if sess.tool_metrics:
            metrics = sess.tool_metrics
        else:
            _click.echo("No tool metrics in session", err=True)
            raise SystemExit(1)

    elif log_file:
        # Parse log file for tool_result events
        import pathlib as _pathlib

        log_path = _pathlib.Path(log_file)
        collector = tools_base.MetricsCollector()

        with log_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = _json.loads(line)
                    if event.get("event_type") == "tool_result":
                        tool_name = event.get("tool_name", "unknown")
                        success = event.get("success", False)
                        duration_ms = event.get("duration_ms", 0.0)
                        collector.record(tool_name, success, duration_ms)
                except _json.JSONDecodeError:
                    continue

        metrics = collector.to_dict()

    else:
        # No source specified - show message
        _click.echo("Specify --log or --session to read tool statistics.", err=True)
        _click.echo()
        _click.echo("Examples:")
        _click.echo("  brynhild tools stats --log ~/.brynhild/logs/brynhild_20251202_143022.jsonl")
        _click.echo("  brynhild tools stats --session abc12345")
        raise SystemExit(1)

    if not metrics:
        _click.echo("No tool usage found", err=True)
        raise SystemExit(1)

    if json_output:
        # Include summary in JSON output
        total_calls = sum(m.get("call_count", 0) for m in metrics.values())
        total_success = sum(m.get("success_count", 0) for m in metrics.values())
        total_duration = sum(m.get("total_duration_ms", 0) for m in metrics.values())
        output = {
            "tools": metrics,
            "summary": {
                "total_calls": total_calls,
                "total_success": total_success,
                "total_failures": total_calls - total_success,
                "success_rate": (total_success / total_calls * 100.0) if total_calls else 0.0,
                "total_duration_ms": round(total_duration, 2),
                "tools_used": len(metrics),
            },
        }
        _click.echo(_json.dumps(output, indent=2))
    else:
        _click.echo("Tool Usage Statistics")
        _click.echo("=" * 60)
        _click.echo()
        _click.echo(f"{'Tool':<15} {'Calls':<8} {'Success':<8} {'Fail':<6} {'Rate':<8} {'Avg ms':<10}")
        _click.echo("-" * 60)

        total_calls = 0
        total_success = 0
        total_duration = 0.0

        # Sort by call count
        sorted_metrics = sorted(metrics.items(), key=lambda x: x[1].get("call_count", 0), reverse=True)

        for tool_name, m in sorted_metrics:
            calls = m.get("call_count", 0)
            success = m.get("success_count", 0)
            failures = m.get("failure_count", 0)
            rate = m.get("success_rate", 0.0)
            avg_ms = m.get("average_duration_ms", 0.0)

            total_calls += calls
            total_success += success
            total_duration += m.get("total_duration_ms", 0.0)

            _click.echo(f"{tool_name:<15} {calls:<8} {success:<8} {failures:<6} {rate:>6.1f}% {avg_ms:>8.1f}")

        _click.echo("-" * 60)
        total_rate = (total_success / total_calls * 100.0) if total_calls else 0.0
        total_avg = (total_duration / total_calls) if total_calls else 0.0
        _click.echo(f"{'TOTAL':<15} {total_calls:<8} {total_success:<8} {total_calls - total_success:<6} {total_rate:>6.1f}% {total_avg:>8.1f}")


# =============================================================================
# Models Command Group
# =============================================================================


@cli.group(name="models")
def models_cmd() -> None:
    """OpenRouter model information and inspection."""
    pass


@models_cmd.command(name="list")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
def models_list(json_output: bool) -> None:
    """List models with shortcuts in brynhild."""
    import brynhild.api.openrouter_provider as openrouter

    models = openrouter.OPENROUTER_MODELS

    if json_output:
        _click.echo(_json.dumps(models, indent=2))
    else:
        _click.echo(f"{'Model ID':<55} {'Name'}")
        _click.echo("-" * 80)
        for model_id, name in sorted(models.items()):
            _click.echo(f"{model_id:<55} {name}")
        _click.echo()
        _click.echo(f"Total: {len(models)} models")


@models_cmd.command(name="compare")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
@_click.option("--sort", "sort_by", type=_click.Choice(["cost", "context", "name"]), default="cost", help="Sort by field")
@_click.option("--tools-only", is_flag=True, help="Only show models with tool support")
@_click.option(
    "--ratio",
    default=20,
    type=int,
    help="Input:output token ratio for blended cost (default: 20, meaning 20:1)",
)
def models_compare(json_output: bool, sort_by: str, tools_only: bool, ratio: int) -> None:
    """Compare models: pricing, context size, and tool support."""
    import httpx as _httpx

    import brynhild.api.openrouter_provider as openrouter

    our_models = list(openrouter.OPENROUTER_MODELS.keys())

    # Query OpenRouter API
    try:
        response = _httpx.get("https://openrouter.ai/api/v1/models", timeout=30.0)
        response.raise_for_status()
        data = response.json()
    except _httpx.HTTPError as e:
        if json_output:
            _click.echo(_json.dumps({"error": str(e)}))
        else:
            _click.echo(f"Error querying OpenRouter API: {e}", err=True)
        raise SystemExit(1) from None

    models_by_id = {m["id"]: m for m in data.get("data", [])}

    results: list[dict[str, _typing.Any]] = []

    for model_id in our_models:
        model = models_by_id.get(model_id)
        if not model:
            results.append({
                "model": model_id,
                "name": openrouter.OPENROUTER_MODELS.get(model_id, ""),
                "found": False,
                "tools": None,
                "context": None,
                "prompt_per_m": None,
                "completion_per_m": None,
                "blended_per_m": None,
            })
            continue

        params = model.get("supported_parameters", [])
        has_tools = "tools" in params
        pricing = model.get("pricing", {})

        prompt_price = float(pricing.get("prompt", 0))
        completion_price = float(pricing.get("completion", 0))

        # Cost per 1M tokens
        prompt_per_m = prompt_price * 1_000_000
        completion_per_m = completion_price * 1_000_000
        # Blended cost: weighted by input:output ratio
        # Real-world coding assistant usage is heavily input-weighted (~20:1 to 200:1)
        blended_per_m = (ratio * prompt_per_m + completion_per_m) / (ratio + 1)

        results.append({
            "model": model_id,
            "name": model.get("name", ""),
            "found": True,
            "tools": has_tools,
            "context": model.get("context_length", 0),
            "prompt_per_m": prompt_per_m,
            "completion_per_m": completion_per_m,
            "blended_per_m": blended_per_m,
        })

    # Filter if needed
    if tools_only:
        results = [r for r in results if r.get("tools") is True]

    # Sort
    if sort_by == "cost":
        results.sort(key=lambda x: x.get("blended_per_m") or 999999)
    elif sort_by == "context":
        results.sort(key=lambda x: -(x.get("context") or 0))
    else:  # name
        results.sort(key=lambda x: x["model"])

    if json_output:
        output = {"models": results, "ratio": ratio}
        _click.echo(_json.dumps(output, indent=2))
    else:
        _click.echo(f"OpenRouter Model Comparison (input:output ratio = {ratio}:1)")
        _click.echo("=" * 115)
        _click.echo(
            f"{'Model':<42} {'Tools':<6} {'Context':<12} "
            f"{'Prompt/M':<10} {'Comp/M':<10} {'Blend/M':<10}"
        )
        _click.echo("-" * 115)

        for r in results:
            model_id = r["model"]
            if not r["found"]:
                _click.echo(f"{model_id:<42} {'?':<6} {'NOT FOUND':<12}")
                continue

            tools_str = "✅" if r["tools"] else "❌"
            ctx = f"{r['context']:,}" if r["context"] else "?"
            prompt = f"${r['prompt_per_m']:.2f}" if r["prompt_per_m"] is not None else "?"
            comp = f"${r['completion_per_m']:.2f}" if r["completion_per_m"] is not None else "?"
            blend = f"${r['blended_per_m']:.2f}" if r["blended_per_m"] is not None else "?"

            _click.echo(
                f"{model_id:<42} {tools_str:<6} {ctx:<12} "
                f"{prompt:<10} {comp:<10} {blend:<10}"
            )

        _click.echo()
        _click.echo("=" * 115)
        tools_count = sum(1 for r in results if r.get("tools") is True)
        _click.echo(f"Total: {len(results)} models, {tools_count} with tool support")
        _click.echo()
        _click.echo(f"Blend = ({ratio} × prompt + 1 × completion) / {ratio + 1}")
        if not tools_only:
            _click.echo("Use --tools-only to filter to models with tool support")


@models_cmd.command(name="tools")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
@_click.option("--all", "show_all", is_flag=True, help="Show all models, not just problematic ones")
def models_tools(json_output: bool, show_all: bool) -> None:
    """Show tool support status for OpenRouter models."""
    import httpx as _httpx

    import brynhild.api.openrouter_provider as openrouter

    our_models = list(openrouter.OPENROUTER_MODELS.keys())

    # Query OpenRouter API
    try:
        response = _httpx.get("https://openrouter.ai/api/v1/models", timeout=30.0)
        response.raise_for_status()
        data = response.json()
    except _httpx.HTTPError as e:
        if json_output:
            _click.echo(_json.dumps({"error": str(e)}))
        else:
            _click.echo(f"Error querying OpenRouter API: {e}", err=True)
        raise SystemExit(1) from None

    models_by_id = {m["id"]: m for m in data.get("data", [])}

    results: list[dict[str, _typing.Any]] = []
    supports_tools: list[str] = []
    no_tools: list[str] = []
    not_found: list[str] = []

    for model_id in our_models:
        model = models_by_id.get(model_id)
        if model:
            params = model.get("supported_parameters", [])
            has_tools = "tools" in params
            has_tool_choice = "tool_choice" in params

            result = {
                "model": model_id,
                "found": True,
                "tools": has_tools,
                "tool_choice": has_tool_choice,
            }
            results.append(result)

            if has_tools:
                supports_tools.append(model_id)
            else:
                no_tools.append(model_id)
        else:
            results.append({
                "model": model_id,
                "found": False,
                "tools": None,
                "tool_choice": None,
            })
            not_found.append(model_id)

    if json_output:
        output = {
            "results": results,
            "summary": {
                "with_tools": len(supports_tools),
                "without_tools": len(no_tools),
                "not_found": len(not_found),
            },
            "without_tools": no_tools,
            "not_found": not_found,
        }
        _click.echo(_json.dumps(output, indent=2))
    else:
        _click.echo("OpenRouter Tool Support Analysis")
        _click.echo("=" * 90)
        _click.echo(f"{'Model':<55} {'Tools':<8} {'Status'}")
        _click.echo("-" * 90)

        for r in results:
            model_id = r["model"]
            if not r["found"]:
                status = "⚠️  NOT FOUND"
                tools_str = "?"
            elif r["tools"]:
                if not show_all:
                    continue  # Skip models with tools unless --all
                status = "✅ TOOLS"
                tools_str = "Yes"
            else:
                status = "❌ NO TOOLS"
                tools_str = "No"

            _click.echo(f"{model_id:<55} {tools_str:<8} {status}")

        _click.echo()
        _click.echo("=" * 90)
        _click.echo(
            f"Summary: {len(supports_tools)} with tools, "
            f"{len(no_tools)} without, {len(not_found)} not found"
        )

        if no_tools and not show_all:
            _click.echo()
            _click.echo("Models WITHOUT tool support:")
            for m in no_tools:
                _click.echo(f"  - {m}")

        if not_found:
            _click.echo()
            _click.echo("Models NOT FOUND on OpenRouter:")
            for m in not_found:
                _click.echo(f"  - {m}")

        if not show_all:
            _click.echo()
            _click.echo("(Use --all to show all models including those with tool support)")


@models_cmd.command(name="info")
@_click.argument("model_id")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
def models_info(model_id: str, json_output: bool) -> None:
    """Show detailed information about a specific model."""
    import httpx as _httpx

    # Query OpenRouter API
    try:
        response = _httpx.get("https://openrouter.ai/api/v1/models", timeout=30.0)
        response.raise_for_status()
        data = response.json()
    except _httpx.HTTPError as e:
        if json_output:
            _click.echo(_json.dumps({"error": str(e)}))
        else:
            _click.echo(f"Error querying OpenRouter API: {e}", err=True)
        raise SystemExit(1) from None

    models_by_id = {m["id"]: m for m in data.get("data", [])}
    model = models_by_id.get(model_id)

    if not model:
        if json_output:
            _click.echo(_json.dumps({"error": f"Model not found: {model_id}"}))
        else:
            _click.echo(f"Error: Model '{model_id}' not found on OpenRouter", err=True)
        raise SystemExit(1) from None

    if json_output:
        _click.echo(_json.dumps(model, indent=2))
    else:
        _click.echo(f"Model: {model['id']}")
        _click.echo(f"Name: {model.get('name', 'N/A')}")
        _click.echo(f"Context Length: {model.get('context_length', 'N/A'):,}")
        _click.echo()

        # Architecture
        arch = model.get("architecture", {})
        _click.echo("Architecture:")
        _click.echo(f"  Modality: {arch.get('modality', 'N/A')}")
        _click.echo(f"  Input: {', '.join(arch.get('input_modalities', []))}")
        _click.echo(f"  Output: {', '.join(arch.get('output_modalities', []))}")
        _click.echo()

        # Pricing
        pricing = model.get("pricing", {})
        _click.echo("Pricing (per token):")
        _click.echo(f"  Prompt: ${float(pricing.get('prompt', 0)):.8f}")
        _click.echo(f"  Completion: ${float(pricing.get('completion', 0)):.8f}")
        _click.echo()

        # Supported parameters
        params = model.get("supported_parameters", [])
        _click.echo(f"Supported Parameters ({len(params)}):")
        has_tools = "tools" in params
        has_tool_choice = "tool_choice" in params
        _click.echo(f"  Tools: {'✅ Yes' if has_tools else '❌ No'}")
        _click.echo(f"  Tool Choice: {'✅ Yes' if has_tool_choice else '❌ No'}")
        _click.echo()
        _click.echo(f"  All: {', '.join(sorted(params))}")

        # Description
        desc = model.get("description", "")
        if desc:
            _click.echo()
            _click.echo("Description:")
            # Word wrap at 80 chars
            import textwrap as _textwrap

            for line in _textwrap.wrap(desc, width=78):
                _click.echo(f"  {line}")


@models_cmd.command(name="search")
@_click.argument("query")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
@_click.option("--limit", default=20, help="Maximum results to show")
def models_search(query: str, json_output: bool, limit: int) -> None:
    """Search for models on OpenRouter by name or ID."""
    import httpx as _httpx

    # Query OpenRouter API
    try:
        response = _httpx.get("https://openrouter.ai/api/v1/models", timeout=30.0)
        response.raise_for_status()
        data = response.json()
    except _httpx.HTTPError as e:
        if json_output:
            _click.echo(_json.dumps({"error": str(e)}))
        else:
            _click.echo(f"Error querying OpenRouter API: {e}", err=True)
        raise SystemExit(1) from None

    query_lower = query.lower()
    matches: list[dict[str, _typing.Any]] = []

    for model in data.get("data", []):
        model_id = model.get("id", "").lower()
        name = model.get("name", "").lower()
        desc = model.get("description", "").lower()

        if query_lower in model_id or query_lower in name or query_lower in desc:
            params = model.get("supported_parameters", [])
            matches.append({
                "id": model["id"],
                "name": model.get("name", ""),
                "tools": "tools" in params,
                "context_length": model.get("context_length", 0),
            })

    # Sort by relevance (exact ID match first, then name match, then description)
    def sort_key(m: dict[str, _typing.Any]) -> tuple[int, str]:
        if query_lower == m["id"].lower():
            return (0, m["id"])
        if query_lower in m["id"].lower():
            return (1, m["id"])
        if query_lower in m["name"].lower():
            return (2, m["id"])
        return (3, m["id"])

    matches.sort(key=sort_key)
    matches = matches[:limit]

    if json_output:
        _click.echo(_json.dumps({"query": query, "results": matches}, indent=2))
    else:
        if not matches:
            _click.echo(f"No models found matching '{query}'")
            return

        _click.echo(f"Models matching '{query}' ({len(matches)} results):")
        _click.echo()
        _click.echo(f"{'Model ID':<50} {'Tools':<7} {'Context'}")
        _click.echo("-" * 75)
        for m in matches:
            tools_str = "✅" if m["tools"] else "❌"
            ctx = f"{m['context_length']:,}" if m["context_length"] else "?"
            _click.echo(f"{m['id']:<50} {tools_str:<7} {ctx}")


# =============================================================================
# Logs Commands
# =============================================================================


@cli.group(name="logs")
def logs_group() -> None:
    """View and manage conversation logs."""
    pass


@logs_group.command(name="list")
@_click.option("--limit", "-n", default=20, help="Number of logs to show")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
@_click.pass_context
def logs_list(ctx: _click.Context, limit: int, json_output: bool) -> None:
    """List recent conversation log files."""
    settings: config.Settings = ctx.obj["settings"]
    log_dir = settings.logs_dir

    if not log_dir.exists():
        if json_output:
            _click.echo(_json.dumps({"logs": [], "log_dir": str(log_dir)}))
        else:
            _click.echo(f"No logs found. Log directory: {log_dir}")
        return

    # Find all log files (exclude raw logs)
    log_files = sorted(
        [f for f in log_dir.glob("brynhild_*.jsonl") if not f.name.startswith("brynhild_raw_")],
        reverse=True,
    )[:limit]

    if json_output:
        logs_data = []
        for f in log_files:
            stat = f.stat()
            logs_data.append({
                "path": str(f),
                "name": f.name,
                "size": stat.st_size,
                "modified": _datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
        _click.echo(_json.dumps({"logs": logs_data, "log_dir": str(log_dir)}, indent=2))
    else:
        if not log_files:
            _click.echo(f"No logs found in {log_dir}")
            return

        _click.echo(f"Conversation logs ({len(log_files)} shown):")
        _click.echo(f"Directory: {log_dir}")
        _click.echo()
        _click.echo(f"{'Filename':<40} {'Size':>10} {'Modified'}")
        _click.echo("-" * 70)
        for f in log_files:
            stat = f.stat()
            size = f"{stat.st_size:,}"
            modified = _datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            _click.echo(f"{f.name:<40} {size:>10} {modified}")


@logs_group.command(name="view")
@_click.argument("log_file", required=False)
@_click.option("--json", "json_output", is_flag=True, help="Raw JSON output (pretty-printed)")
@_click.option("--raw", is_flag=True, help="Raw JSONL (one JSON per line)")
@_click.option("--summary", is_flag=True, help="Show truncated summary instead of full content")
@_click.pass_context
def logs_view(
    ctx: _click.Context,
    log_file: str | None,
    json_output: bool,
    raw: bool,
    summary: bool,
) -> None:
    """View a conversation log file.

    If LOG_FILE is not specified, shows the most recent log.
    By default shows full content. Use --summary for truncated view.
    """
    settings: config.Settings = ctx.obj["settings"]
    log_path = _resolve_log_path(log_file, settings.logs_dir)

    # Read and display
    events = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(_json.loads(line))
                except _json.JSONDecodeError:
                    continue

    if json_output:
        for event in events:
            _click.echo(_json.dumps(event, indent=2))
        return

    if raw:
        for event in events:
            _click.echo(_json.dumps(event))
        return

    # Pretty-print the conversation
    _click.echo(f"📁 Log: {log_path.name}")
    _click.echo("=" * 70)
    _click.echo()

    for event in events:
        event_type = event.get("event_type", "unknown")
        timestamp = event.get("timestamp", "")[:19]  # Trim microseconds

        if event_type == "session_start":
            _click.echo(f"🚀 Session started at {timestamp}")
            _click.echo(f"   Provider: {event.get('provider')}")
            _click.echo(f"   Model: {event.get('model')}")
            _click.echo()

        elif event_type == "system_prompt":
            content = event.get("content", "")
            _click.echo(f"📋 System prompt ({len(content)} chars)")
            _click.echo("-" * 40)
            if summary:
                preview = content[:200] + "..." if len(content) > 200 else content
                _click.echo(preview)
            else:
                _click.echo(content)
            _click.echo("-" * 40)
            _click.echo()

        elif event_type == "user_message":
            content = event.get("content", "")
            _click.echo(f"👤 User [{timestamp}]")
            _click.echo("-" * 40)
            if summary:
                lines = content.split("\n")
                for line in lines[:10]:
                    _click.echo(line)
                if len(lines) > 10:
                    _click.echo(f"... ({len(lines) - 10} more lines)")
            else:
                _click.echo(content)
            _click.echo("-" * 40)
            _click.echo()

        elif event_type == "assistant_message":
            content = event.get("content", "")
            thinking = event.get("thinking")
            _click.echo(f"🤖 Assistant [{timestamp}]")
            if thinking:
                _click.echo(f"💭 Thinking ({len(thinking)} chars):")
                _click.echo("-" * 40)
                if summary:
                    preview = thinking[:300] + "..." if len(thinking) > 300 else thinking
                    _click.echo(preview)
                else:
                    _click.echo(thinking)
                _click.echo("-" * 40)
            _click.echo("Response:")
            _click.echo("-" * 40)
            if summary:
                lines = content.split("\n")
                for line in lines[:20]:
                    _click.echo(line)
                if len(lines) > 20:
                    _click.echo(f"... ({len(lines) - 20} more lines)")
            else:
                _click.echo(content)
            _click.echo("-" * 40)
            _click.echo()

        elif event_type == "tool_call":
            _click.echo(f"🔧 Tool call: {event.get('tool_name')} [{timestamp}]")
            tool_input = event.get("tool_input", {})
            _click.echo("Input:")
            for k, v in tool_input.items():
                v_str = str(v)
                if summary and len(v_str) > 100:
                    v_str = v_str[:100] + "..."
                _click.echo(f"  {k}: {v_str}")
            _click.echo()

        elif event_type == "tool_result":
            success = "✅" if event.get("success") else "❌"
            _click.echo(f"{success} Tool result: {event.get('tool_name')}")
            if event.get("error"):
                error = event.get("error", "")
                _click.echo("Error:")
                _click.echo("-" * 40)
                if summary and len(error) > 200:
                    _click.echo(error[:200] + "...")
                else:
                    _click.echo(error)
                _click.echo("-" * 40)
            elif event.get("output"):
                output = event.get("output", "")
                _click.echo("Output:")
                _click.echo("-" * 40)
                if summary and len(output) > 500:
                    _click.echo(output[:500] + "...")
                else:
                    _click.echo(output)
                _click.echo("-" * 40)
            _click.echo()
            _click.echo()

        elif event_type == "error":
            _click.echo(f"❌ Error [{timestamp}]")
            _click.echo(f"   {event.get('error')}")
            if event.get("context"):
                _click.echo(f"   Context: {event.get('context')}")
            _click.echo()

        elif event_type == "thinking":
            # Standalone thinking event (when model produces thinking separately)
            thinking = event.get("content", "")
            _click.echo(f"💭 Thinking [{timestamp}] ({len(thinking)} chars)")
            _click.echo("-" * 40)
            if summary:
                preview = thinking[:300] + "..." if len(thinking) > 300 else thinking
                _click.echo(preview)
            else:
                _click.echo(thinking)
            _click.echo("-" * 40)
            _click.echo()

        elif event_type == "thinking_only_response":
            # Model produced only thinking, no actual output
            thinking = event.get("thinking", "")
            attempt = event.get("retry_attempt", "?")
            _click.echo(f"⚠️ Thinking-only response [{timestamp}] (attempt {attempt}/3)")
            _click.echo("-" * 40)
            if summary:
                preview = thinking[:300] + "..." if len(thinking) > 300 else thinking
                _click.echo(preview)
            else:
                _click.echo(thinking)
            _click.echo("-" * 40)
            _click.echo()

        elif event_type == "thinking_retry_feedback":
            # Feedback sent to model to prompt proper output
            _click.echo(f"↩️ Retry feedback sent [{timestamp}]")
            error_msg = event.get("error_message", "")
            if summary:
                _click.echo(f"   (tool_call_id: {event.get('tool_call_id', '?')})")
            else:
                _click.echo(f"   Tool call ID: {event.get('tool_call_id')}")
                _click.echo(f"   Message: {error_msg[:200]}...")
            _click.echo()

        elif event_type == "usage":
            # Token usage and cost
            input_tokens = event.get("input_tokens", 0)
            output_tokens = event.get("output_tokens", 0)
            cost = event.get("cost_usd")
            reasoning = event.get("reasoning_tokens")
            provider = event.get("provider")
            gen_id = event.get("generation_id")

            cost_str = f" | ${cost:.6f}" if cost else ""
            reasoning_str = f" (reasoning: {reasoning})" if reasoning else ""
            provider_str = f" via {provider}" if provider else ""

            _click.echo(
                f"📊 Usage [{timestamp}]: {input_tokens} in / {output_tokens} out"
                f"{reasoning_str}{cost_str}{provider_str}"
            )
            if gen_id and not summary:
                _click.echo(f"   Generation ID: {gen_id}")
            _click.echo()

        elif event_type == "no_usage_reported":
            _click.echo(f"⚠️ No usage reported [{timestamp}]")
            _click.echo()

        elif event_type == "session_end":
            _click.echo(f"🏁 Session ended ({event.get('total_events', 0)} events)")
            _click.echo()


@logs_group.command(name="export")
@_click.argument("log_file", required=False)
@_click.option(
    "-o",
    "--output",
    type=str,
    default="-",
    help="Output file path (use '-' for stdout)",
)
@_click.option(
    "--title",
    type=str,
    default=None,
    help="Title for markdown output (default: session ID)",
)
@_click.option(
    "--thinking/--no-thinking",
    "include_thinking",
    default=True,
    help="Include thinking sections",
)
@_click.option(
    "--thinking-style",
    type=_click.Choice(["collapsible", "full", "summary", "hidden"]),
    default="collapsible",
    help="How to render thinking content",
)
@_click.pass_context
def logs_export(
    ctx: _click.Context,
    log_file: str | None,
    output: str,
    title: str | None,
    include_thinking: bool,
    thinking_style: str,
) -> None:
    """Export a conversation log to presentation markdown.

    If LOG_FILE is not specified, exports the most recent log.
    Use '-o -' to print to stdout.

    Examples:

        brynhild logs export -o session.md

        brynhild logs export -o -  # print to stdout

        brynhild logs export brynhild_20251205.jsonl -o report.md --title "Code Review"

        brynhild logs export -o report.md --no-thinking
    """
    settings: config.Settings = ctx.obj["settings"]
    log_path = _resolve_log_path(log_file, settings.logs_dir)

    # Read events
    events: list[dict[str, _typing.Any]] = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(_json.loads(line))
                except _json.JSONDecodeError:
                    continue

    if not events:
        _click.echo(f"No events found in {log_path}", err=True)
        raise SystemExit(1)

    # Generate markdown
    markdown = logging.export_log_to_markdown(
        events,
        title=title,
        include_thinking=include_thinking,
        thinking_style=thinking_style,
    )

    # Write output
    if output == "-":
        # Print to stdout
        _click.echo(markdown)
    else:
        # Write to file
        output_path = _pathlib.Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")

        _click.echo(f"✅ Exported to {output}", err=True)
        _click.echo(f"   Source: {log_path.name}", err=True)
        _click.echo(f"   Events: {len(events)}", err=True)


@logs_group.command(name="raw")
@_click.argument("log_file", required=False)
@_click.option("--list", "list_files", is_flag=True, help="List available raw log files")
@_click.option("--index", "-i", type=str, default=None, help="Show specific record(s): '0', '0-5', '0,2,4'")
@_click.option("--direction", "-d", type=str, default=None, help="Filter by direction: request, response, error, stream_complete, meta")
@_click.option("--json", "json_output", is_flag=True, help="Raw JSON output (pretty-printed)")
@_click.option("--summary", is_flag=True, help="Show truncated payload")
@_click.option("--limit", "-n", default=None, type=int, help="Limit number of records shown")
@_click.pass_context
def logs_raw(
    ctx: _click.Context,
    log_file: str | None,
    list_files: bool,
    index: str | None,
    direction: str | None,
    json_output: bool,
    summary: bool,
    limit: int | None,
) -> None:
    """View raw API payload logs.

    Raw logs capture the exact JSON sent to and received from LLM providers.
    Use --raw-log flag when running brynhild to enable raw logging.

    \b
    Examples:
        brynhild logs raw --list              # List available raw log files
        brynhild logs raw                     # View most recent raw log
        brynhild logs raw -i 0                # Show first record only
        brynhild logs raw -i 1-3              # Show records 1, 2, 3
        brynhild logs raw -d request          # Show only requests
        brynhild logs raw -d response         # Show only responses
        brynhild logs raw --summary           # Truncate large payloads
    """
    settings: config.Settings = ctx.obj["settings"]
    log_dir = settings.logs_dir

    # List files mode
    if list_files:
        if not log_dir.exists():
            _click.echo(f"No raw logs found. Log directory: {log_dir}")
            return

        raw_files = sorted(log_dir.glob("brynhild_raw_*.jsonl"), reverse=True)
        if not raw_files:
            _click.echo(f"No raw log files found in {log_dir}")
            _click.echo("Use --raw-log flag when running brynhild chat to enable raw logging.")
            return

        _click.echo(f"Raw payload logs ({len(raw_files)} found):")
        _click.echo(f"Directory: {log_dir}")
        _click.echo()
        _click.echo(f"{'Filename':<45} {'Records':>8} {'Req/Res':>8} {'Size':>10} {'Modified'}")
        _click.echo("-" * 95)
        for f in raw_files[:20]:  # Show up to 20
            stat = f.stat()
            size = f"{stat.st_size:,}"
            modified = _datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")

            # Count records and extract metadata
            record_count = 0
            request_count = 0
            response_count = 0
            try:
                with open(f, encoding="utf-8") as log_f:
                    for line in log_f:
                        line = line.strip()
                        if line:
                            try:
                                record = _json.loads(line)
                                record_count += 1
                                direction = record.get("direction")
                                if direction == "request":
                                    request_count += 1
                                elif direction in ("response", "stream_complete"):
                                    response_count += 1
                            except _json.JSONDecodeError:
                                pass
            except OSError:
                pass

            req_res = f"{request_count}/{response_count}"
            _click.echo(f"{f.name:<45} {record_count:>8} {req_res:>8} {size:>10} {modified}")
        return

    # Determine which file to view
    log_path = _resolve_log_path(
        log_file,
        log_dir,
        pattern="brynhild_raw_*.jsonl",
        exclude_prefix=None,
        error_message="No raw log files found",
    )

    # Read all records
    records: list[dict[str, _typing.Any]] = []
    with open(log_path, encoding="utf-8") as log_f:
        for line in log_f:
            line = line.strip()
            if line:
                try:
                    records.append(_json.loads(line))
                except _json.JSONDecodeError:
                    continue

    # Parse index filter
    indices_to_show: set[int] | None = None
    if index is not None:
        indices_to_show = set()
        for part in index.split(","):
            part = part.strip()
            if "-" in part:
                start, end = part.split("-", 1)
                try:
                    indices_to_show.update(range(int(start), int(end) + 1))
                except ValueError:
                    _click.echo(f"Invalid index range: {part}", err=True)
                    raise SystemExit(1) from None
            else:
                try:
                    indices_to_show.add(int(part))
                except ValueError:
                    _click.echo(f"Invalid index: {part}", err=True)
                    raise SystemExit(1) from None

    # Filter and display
    filtered_records: list[tuple[int, dict[str, _typing.Any]]] = []
    for i, record in enumerate(records):
        # Apply index filter
        if indices_to_show is not None and i not in indices_to_show:
            continue
        # Apply direction filter
        if direction is not None and record.get("direction") != direction:
            continue
        filtered_records.append((i, record))

    # Apply limit
    if limit is not None:
        filtered_records = filtered_records[:limit]

    if json_output:
        for i, record in filtered_records:
            _click.echo(f"// Record {i}")
            _click.echo(_json.dumps(record, indent=2))
        return

    # Pretty-print the records
    _click.echo(f"📁 Raw Log: {log_path.name}")
    _click.echo(f"   Total records: {len(records)}")
    if direction:
        _click.echo(f"   Filter: direction={direction}")
    if indices_to_show:
        _click.echo(f"   Filter: indices={sorted(indices_to_show)}")
    _click.echo("=" * 80)
    _click.echo()

    direction_icons = {
        "meta": "ℹ️",
        "request": "📤",
        "response": "📥",
        "stream_complete": "✅",
        "stream_chunk": "📦",
        "error": "❌",
    }

    def _render_payload_readable(payload: dict[str, _typing.Any], indent: str = "") -> None:
        """Render payload with content fields as readable text, messages last."""
        # Separate messages from other keys - render messages last for easy viewing
        messages_value = None
        other_keys: list[tuple[str, _typing.Any]] = []
        for key, value in payload.items():
            if key == "messages":
                messages_value = value
            else:
                other_keys.append((key, value))

        # Render non-message keys first
        for key, value in other_keys:
            if key == "content" and isinstance(value, str):
                # Render content as readable text
                _click.echo(f"{indent}{key}:")
                content_lines = value.split("\n")
                if summary and len(content_lines) > 20:
                    for line in content_lines[:20]:
                        _click.echo(f"{indent}  {line}")
                    _click.echo(f"{indent}  ... ({len(content_lines)} lines total)")
                else:
                    for line in content_lines:
                        _click.echo(f"{indent}  {line}")
            elif key == "tools" and isinstance(value, list):
                _click.echo(f"{indent}{key}: [{len(value)} tools]")
                if not summary:
                    for tool in value:
                        name = tool.get("function", {}).get("name", "?")
                        _click.echo(f"{indent}  - {name}")
            elif isinstance(value, dict):
                _click.echo(f"{indent}{key}: {_json.dumps(value)}")
            elif isinstance(value, list):
                if len(str(value)) > 100:
                    _click.echo(f"{indent}{key}: [{len(value)} items]")
                else:
                    _click.echo(f"{indent}{key}: {_json.dumps(value)}")
            else:
                _click.echo(f"{indent}{key}: {value}")

        # Render messages last
        if messages_value is not None and isinstance(messages_value, list):
            _click.echo(f"{indent}messages:")
            for j, msg in enumerate(messages_value):
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                _click.echo(f"{indent}  [{j}] {role}:")
                if content:
                    # Render content as readable text (not JSON escaped)
                    content_lines = str(content).split("\n")
                    if summary and len(content_lines) > 10:
                        for line in content_lines[:10]:
                            _click.echo(f"{indent}      {line}")
                        _click.echo(f"{indent}      ... ({len(content_lines)} lines total)")
                    else:
                        for line in content_lines:
                            _click.echo(f"{indent}      {line}")
                # Show tool_calls if present
                if "tool_calls" in msg:
                    tc_json = _json.dumps(msg["tool_calls"], indent=2)
                    tc_lines = tc_json.split("\n")
                    _click.echo(f"{indent}      tool_calls:")
                    for tc_line in tc_lines:
                        _click.echo(f"{indent}        {tc_line}")

    for i, record in filtered_records:
        dir_type = record.get("direction", "unknown")
        icon = direction_icons.get(dir_type, "❓")
        timestamp = record.get("timestamp", "")[:19]
        endpoint = record.get("endpoint", "")
        duration = record.get("duration_ms")
        provider = record.get("provider", "")
        model = record.get("model", "")

        # Header block (JSON-style metadata)
        _click.echo(f"[{i}] {icon} {dir_type.upper()}")
        _click.echo("-" * 60)
        _click.echo(f"  endpoint: {endpoint}")
        _click.echo(f"  timestamp: {timestamp}")
        if provider:
            _click.echo(f"  provider: {provider}")
        if model:
            _click.echo(f"  model: {model}")
        if duration:
            _click.echo(f"  duration_ms: {duration:.0f}")

        # Error message if present
        if record.get("error"):
            _click.echo(f"  error: {record['error']}")

        # Payload - render readable
        payload = record.get("payload", {})
        if payload:
            _click.echo("-" * 60)
            _render_payload_readable(payload, indent="  ")

        _click.echo()


# =============================================================================
# Hooks Commands
# =============================================================================


@cli.group(name="hooks")
def hooks_group() -> None:
    """Hook system management commands."""
    pass


@hooks_group.command(name="list")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
@_click.option("--event", type=str, default=None, help="Filter by event type")
@_click.pass_context
def hooks_list(ctx: _click.Context, json_output: bool, event: str | None) -> None:
    """List configured hooks (global + project)."""
    import brynhild.hooks.config as hooks_config
    import brynhild.hooks.events as hooks_events

    settings: config.Settings = ctx.obj["settings"]

    # Load merged config
    merged = hooks_config.load_merged_config(settings.project_root)

    # Build output
    hooks_data: list[dict[str, _typing.Any]] = []

    for event_name, hook_list in merged.hooks.items():
        if event and event_name != event:
            continue

        for hook in hook_list:
            hooks_data.append({
                "event": event_name,
                "name": hook.name,
                "type": hook.type,
                "enabled": hook.enabled,
                "timeout": hook.timeout.seconds,
            })

    if json_output:
        _click.echo(_json.dumps({
            "hooks": hooks_data,
            "global_config": str(hooks_config.get_global_hooks_path()),
            "project_config": str(hooks_config.get_project_hooks_path(settings.project_root)),
        }, indent=2))
    else:
        global_path = hooks_config.get_global_hooks_path()
        project_path = hooks_config.get_project_hooks_path(settings.project_root)

        _click.echo("Hook Configuration:")
        _click.echo(f"  Global: {global_path} {'✓' if global_path.exists() else '(not found)'}")
        _click.echo(f"  Project: {project_path} {'✓' if project_path.exists() else '(not found)'}")
        _click.echo()

        if not hooks_data:
            _click.echo("No hooks configured.")
            return

        _click.echo("Configured Hooks:")
        _click.echo(f"{'Event':<20} {'Name':<25} {'Type':<10} {'Enabled':<8}")
        _click.echo("-" * 70)
        for h in hooks_data:
            enabled = "✓" if h["enabled"] else "✗"
            _click.echo(f"{h['event']:<20} {h['name']:<25} {h['type']:<10} {enabled:<8}")

        # Show available events
        _click.echo()
        _click.echo("Available events:")
        for ev in hooks_events.HookEvent:
            block = "can block" if ev.can_block else "no block"
            modify = "can modify" if ev.can_modify else "no modify"
            _click.echo(f"  {ev.value:<20} ({block}, {modify})")


@hooks_group.command(name="validate")
@_click.argument("config_file", required=False)
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
@_click.pass_context
def hooks_validate(
    ctx: _click.Context,
    config_file: str | None,
    json_output: bool,
) -> None:
    """Validate a hooks configuration file.

    If CONFIG_FILE is not specified, validates both global and project configs.
    """
    import brynhild.hooks.config as hooks_config

    settings: config.Settings = ctx.obj["settings"]
    results: list[dict[str, _typing.Any]] = []

    if config_file:
        # Validate specific file
        paths = [_pathlib.Path(config_file)]
    else:
        # Validate both global and project
        paths = [
            hooks_config.get_global_hooks_path(),
            hooks_config.get_project_hooks_path(settings.project_root),
        ]

    for path in paths:
        result: dict[str, _typing.Any] = {
            "path": str(path),
            "exists": path.exists(),
            "valid": False,
            "error": None,
            "hooks_count": 0,
        }

        if path.exists():
            try:
                cfg = hooks_config.load_hooks_yaml(path)
                result["valid"] = True
                result["hooks_count"] = sum(len(h) for h in cfg.hooks.values())
            except ValueError as e:
                result["error"] = str(e)

        results.append(result)

    if json_output:
        _click.echo(_json.dumps({"results": results}, indent=2))
    else:
        for r in results:
            _click.echo(f"File: {r['path']}")
            if not r["exists"]:
                _click.echo("  Status: not found")
            elif r["valid"]:
                _click.echo(f"  Status: ✓ valid ({r['hooks_count']} hooks)")
            else:
                _click.echo("  Status: ✗ invalid")
                _click.echo(f"  Error: {r['error']}")
            _click.echo()


@hooks_group.command(name="test")
@_click.argument("event_name")
@_click.option("--tool", type=str, default="Bash", help="Tool name for tool events")
@_click.option("--input", "tool_input", type=str, default='{"command": "echo test"}', help="Tool input JSON")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
@_click.pass_context
def hooks_test(
    ctx: _click.Context,
    event_name: str,
    tool: str,
    tool_input: str,
    json_output: bool,
) -> None:
    """Test hooks for an event with mock context.

    EVENT_NAME should be one of: session_start, session_end, pre_tool_use,
    post_tool_use, pre_message, post_message, user_prompt_submit, pre_compact, error
    """
    import brynhild.hooks.events as hooks_events
    import brynhild.hooks.manager as hooks_manager

    settings: config.Settings = ctx.obj["settings"]

    # Parse event name
    try:
        event = hooks_events.HookEvent(event_name)
    except ValueError:
        valid_events = [e.value for e in hooks_events.HookEvent]
        if json_output:
            _click.echo(_json.dumps({"error": f"Invalid event: {event_name}", "valid_events": valid_events}))
        else:
            _click.echo(f"Error: Invalid event '{event_name}'", err=True)
            _click.echo(f"Valid events: {', '.join(valid_events)}", err=True)
        raise SystemExit(1) from None

    # Parse tool input
    try:
        parsed_input = _json.loads(tool_input)
    except _json.JSONDecodeError as e:
        if json_output:
            _click.echo(_json.dumps({"error": f"Invalid JSON for --input: {e}"}))
        else:
            _click.echo(f"Error: Invalid JSON for --input: {e}", err=True)
        raise SystemExit(1) from None

    # Create hook manager
    hook_mgr = hooks_manager.HookManager.from_config(settings.project_root)

    # Check if any hooks are configured for this event
    hooks = hook_mgr.get_hooks_for_event(event)
    if not hooks:
        if json_output:
            _click.echo(_json.dumps({"event": event_name, "hooks": [], "result": "no_hooks"}))
        else:
            _click.echo(f"No hooks configured for event: {event_name}")
        return

    # Create mock context
    context = hooks_events.HookContext(
        event=event,
        session_id="test-session",
        cwd=settings.project_root,
        tool=tool if event in (hooks_events.HookEvent.PRE_TOOL_USE, hooks_events.HookEvent.POST_TOOL_USE) else None,
        tool_input=parsed_input if event == hooks_events.HookEvent.PRE_TOOL_USE else None,
    )

    # Dispatch event
    result = _run_async(hook_mgr.dispatch(event, context))

    if json_output:
        _click.echo(_json.dumps({
            "event": event_name,
            "hooks": [{"name": h.name, "type": h.type} for h in hooks],
            "result": result.to_dict(),
        }, indent=2))
    else:
        _click.echo(f"Testing event: {event_name}")
        _click.echo(f"Hooks configured: {len(hooks)}")
        for h in hooks:
            _click.echo(f"  - {h.name} ({h.type})")
        _click.echo()
        _click.echo(f"Result: {result.action.value}")
        if result.message:
            _click.echo(f"Message: {result.message}")
        if result.modified_input:
            _click.echo(f"Modified input: {_json.dumps(result.modified_input)}")


# =============================================================================
# Plugin Commands
# =============================================================================


@cli.group(name="plugin")
def plugin_group() -> None:
    """Plugin management commands."""
    pass


@plugin_group.command(name="list")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
@_click.pass_context
def plugin_list(ctx: _click.Context, json_output: bool) -> None:
    """List all discovered plugins."""
    import brynhild.plugins as plugins

    settings: config.Settings = ctx.obj["settings"]
    registry = plugins.PluginRegistry(project_root=settings.project_root)

    plugin_list = registry.list_plugins()

    if json_output:
        _click.echo(_json.dumps(registry.to_dict(), indent=2))
    else:
        _click.echo("Plugin Discovery Paths:")
        for path in plugins.get_plugin_search_paths(settings.project_root):
            exists = "✓" if path.exists() else "(not found)"
            _click.echo(f"  {path} {exists}")
        _click.echo()

        if not plugin_list:
            _click.echo("No plugins found.")
            return

        _click.echo(f"Discovered Plugins ({len(plugin_list)}):")
        _click.echo(f"{'Name':<25} {'Version':<10} {'Enabled':<8} {'Source'}")
        _click.echo("-" * 70)
        for p in plugin_list:
            enabled = "✓" if p.enabled else "✗"
            _click.echo(f"{p.name:<25} {p.version:<10} {enabled:<8} {p.path}")


@plugin_group.command(name="show")
@_click.argument("name")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
@_click.pass_context
def plugin_show(ctx: _click.Context, name: str, json_output: bool) -> None:
    """Show details for a specific plugin."""
    import brynhild.plugins as plugins

    settings: config.Settings = ctx.obj["settings"]
    registry = plugins.PluginRegistry(project_root=settings.project_root)

    plugin = registry.get_plugin(name)

    if plugin is None:
        if json_output:
            _click.echo(_json.dumps({"error": f"Plugin not found: {name}"}))
        else:
            _click.echo(f"Error: Plugin '{name}' not found", err=True)
        raise SystemExit(1)

    if json_output:
        _click.echo(_json.dumps(plugin.to_dict(), indent=2))
    else:
        _click.echo(f"Plugin: {plugin.name}")
        _click.echo(f"  Version: {plugin.version}")
        _click.echo(f"  Description: {plugin.description or '(none)'}")
        _click.echo(f"  Path: {plugin.path}")
        _click.echo(f"  Enabled: {'✓' if plugin.enabled else '✗'}")
        _click.echo()
        _click.echo("Components:")
        _click.echo(f"  Commands: {plugin.manifest.commands or '(none)'}")
        _click.echo(f"  Tools: {plugin.manifest.tools or '(none)'}")
        _click.echo(f"  Hooks: {'yes' if plugin.manifest.hooks else 'no'}")
        _click.echo(f"  Skills: {plugin.manifest.skills or '(none)'}")


@plugin_group.command(name="paths")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
@_click.pass_context
def plugin_paths(ctx: _click.Context, json_output: bool) -> None:
    """Show plugin discovery paths and how they're configured."""
    import os as _os

    import brynhild.plugins as plugins

    settings: config.Settings = ctx.obj["settings"]
    search_paths = plugins.get_plugin_search_paths(settings.project_root)

    if json_output:
        data = {
            "search_paths": [
                {
                    "path": str(p),
                    "exists": p.exists(),
                    "source": _get_path_source(p, settings),
                }
                for p in search_paths
            ],
            "env_vars": {
                "BRYNHILD_PLUGIN_PATH": _os.environ.get("BRYNHILD_PLUGIN_PATH", ""),
                "BRYNHILD_ENABLED_PLUGINS": _os.environ.get(
                    "BRYNHILD_ENABLED_PLUGINS", ""
                ),
            },
        }
        _click.echo(_json.dumps(data, indent=2))
    else:
        _click.echo("Plugin Discovery Paths (searched in order):")
        _click.echo()
        for i, path in enumerate(search_paths, 1):
            exists = "✓ exists" if path.exists() else "✗ not found"
            source = _get_path_source(path, settings)
            _click.echo(f"  {i}. {path}")
            _click.echo(f"     [{exists}] ({source})")
            _click.echo()

        _click.echo("Environment Variables:")
        plugin_path = _os.environ.get("BRYNHILD_PLUGIN_PATH", "")
        enabled = _os.environ.get("BRYNHILD_ENABLED_PLUGINS", "")
        _click.echo(f"  BRYNHILD_PLUGIN_PATH: {plugin_path or '(not set)'}")
        _click.echo(f"  BRYNHILD_ENABLED_PLUGINS: {enabled or '(not set)'}")
        _click.echo()
        _click.echo("Notes:")
        _click.echo("  - Plugins are discovered in order; first match wins")
        _click.echo("  - Set BRYNHILD_PLUGIN_PATH to add custom paths (colon-separated)")
        _click.echo("  - Set BRYNHILD_ENABLED_PLUGINS to filter which plugins load")


def _get_path_source(path: _pathlib.Path, settings: _typing.Any) -> str:
    """Determine the source/reason for a plugin path."""
    import os as _os

    path_str = str(path)

    # Check if from environment variable
    env_path = _os.environ.get("BRYNHILD_PLUGIN_PATH", "")
    if env_path:
        for p in env_path.split(":"):
            if p and path_str == str(_pathlib.Path(p).expanduser().resolve()):
                return "from BRYNHILD_PLUGIN_PATH"

    # Check if global plugins dir
    global_dir = _pathlib.Path.home() / ".config" / "brynhild" / "plugins"
    if path == global_dir:
        return "global plugins directory"

    # Check if project plugins dir
    project_root = getattr(settings, "project_root", None)
    if project_root:
        project_plugins = project_root / ".brynhild" / "plugins"
        if path == project_plugins:
            return "project plugins directory"

    return "configured"


@plugin_group.command(name="enable")
@_click.argument("name")
@_click.pass_context
def plugin_enable(ctx: _click.Context, name: str) -> None:
    """Enable a plugin."""
    import brynhild.plugins as plugins

    settings: config.Settings = ctx.obj["settings"]
    registry = plugins.PluginRegistry(project_root=settings.project_root)

    if registry.enable(name):
        _click.echo(f"Plugin '{name}' enabled.")
    else:
        plugin = registry.get_plugin(name)
        if plugin is None:
            _click.echo(f"Error: Plugin '{name}' not found", err=True)
            raise SystemExit(1)
        else:
            _click.echo(f"Plugin '{name}' is already enabled.")


@plugin_group.command(name="disable")
@_click.argument("name")
@_click.pass_context
def plugin_disable(ctx: _click.Context, name: str) -> None:
    """Disable a plugin."""
    import brynhild.plugins as plugins

    settings: config.Settings = ctx.obj["settings"]
    registry = plugins.PluginRegistry(project_root=settings.project_root)

    if registry.disable(name):
        _click.echo(f"Plugin '{name}' disabled.")
    else:
        plugin = registry.get_plugin(name)
        if plugin is None:
            _click.echo(f"Error: Plugin '{name}' not found", err=True)
            raise SystemExit(1)
        else:
            _click.echo(f"Plugin '{name}' is already disabled.")


@plugin_group.command(name="validate")
@_click.argument("path")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
def plugin_validate(path: str, json_output: bool) -> None:
    """Validate a plugin directory."""
    import brynhild.plugins as plugins

    plugin_path = _pathlib.Path(path)
    loader = plugins.PluginLoader()

    result: dict[str, _typing.Any] = {
        "path": str(plugin_path),
        "valid": False,
        "warnings": [],
        "error": None,
    }

    try:
        warnings = loader.validate(plugin_path)
        result["valid"] = True
        result["warnings"] = warnings
    except (FileNotFoundError, ValueError) as e:
        result["error"] = str(e)

    if json_output:
        _click.echo(_json.dumps(result, indent=2))
    else:
        _click.echo(f"Plugin: {plugin_path}")
        if result["error"]:
            _click.echo("  Status: ✗ invalid")
            _click.echo(f"  Error: {result['error']}")
        elif result["warnings"]:
            _click.echo("  Status: ⚠ valid with warnings")
            for warning in result["warnings"]:
                _click.echo(f"  Warning: {warning}")
        else:
            _click.echo("  Status: ✓ valid")


# =============================================================================
# Skill Commands
# =============================================================================


@cli.group(name="skill")
def skill_group() -> None:
    """Skill management commands."""
    pass


@skill_group.command(name="list")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
@_click.pass_context
def skill_list(ctx: _click.Context, json_output: bool) -> None:
    """List all discovered skills."""
    import brynhild.plugins.registry as plugin_registry
    import brynhild.skills as skills

    settings: config.Settings = ctx.obj["settings"]
    plugins_reg = plugin_registry.PluginRegistry(project_root=settings.project_root)
    plugins = list(plugins_reg.get_enabled_plugins())
    registry = skills.SkillRegistry(
        project_root=settings.project_root,
        plugins=plugins,
    )

    skill_list = registry.list_skills()

    if json_output:
        _click.echo(_json.dumps(registry.to_dict(), indent=2))
    else:
        _click.echo("Skill Discovery Paths:")
        for path in skills.get_skill_search_paths(settings.project_root):
            exists = "✓" if path.exists() else "(not found)"
            _click.echo(f"  {path} {exists}")
        _click.echo()

        if not skill_list:
            _click.echo("No skills found.")
            return

        _click.echo(f"Discovered Skills ({len(skill_list)}):")
        _click.echo(f"{'Name':<30} {'Lines':<8} {'Source'}")
        _click.echo("-" * 70)
        for s in skill_list:
            limit_warn = " ⚠" if s.exceeds_soft_limit else ""
            _click.echo(f"{s.name:<30} {s.body_line_count:<8}{limit_warn} {s.source}")


@skill_group.command(name="show")
@_click.argument("name")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
@_click.option("--body", is_flag=True, help="Show full skill body")
@_click.pass_context
def skill_show(
    ctx: _click.Context, name: str, json_output: bool, body: bool
) -> None:
    """Show details for a specific skill."""
    import brynhild.plugins.registry as plugin_registry
    import brynhild.skills as skills

    settings: config.Settings = ctx.obj["settings"]
    plugins_reg = plugin_registry.PluginRegistry(project_root=settings.project_root)
    plugins = list(plugins_reg.get_enabled_plugins())
    registry = skills.SkillRegistry(
        project_root=settings.project_root,
        plugins=plugins,
    )

    skill = registry.get_skill(name)

    if skill is None:
        if json_output:
            _click.echo(_json.dumps({"error": f"Skill not found: {name}"}))
        else:
            _click.echo(f"Error: Skill '{name}' not found", err=True)
        raise SystemExit(1)

    if json_output:
        data = skill.to_dict()
        if body:
            data["body"] = skill.body
        _click.echo(_json.dumps(data, indent=2))
    else:
        _click.echo(f"Skill: {skill.name}")
        _click.echo(f"  Description: {skill.description}")
        _click.echo(f"  Path: {skill.path}")
        _click.echo(f"  Source: {skill.source}")
        _click.echo(f"  Body lines: {skill.body_line_count}")
        if skill.exceeds_soft_limit:
            _click.echo(f"  ⚠ Exceeds recommended limit of {skills.SKILL_BODY_SOFT_LIMIT} lines")
        if skill.license:
            _click.echo(f"  License: {skill.license}")
        if skill.allowed_tools:
            _click.echo(f"  Allowed tools: {skill.allowed_tools}")

        refs = skill.list_reference_files()
        if refs:
            _click.echo()
            _click.echo("Reference files:")
            for ref in refs:
                _click.echo(f"  - {ref.name}")

        scripts = skill.list_scripts()
        if scripts:
            _click.echo()
            _click.echo("Scripts:")
            for script in scripts:
                _click.echo(f"  - {script.name}")

        if body:
            _click.echo()
            _click.echo("--- Body ---")
            _click.echo(skill.body)


@skill_group.command(name="validate")
@_click.argument("path")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
def skill_validate(path: str, json_output: bool) -> None:
    """Validate a skill directory."""
    import brynhild.skills as skills

    skill_path = _pathlib.Path(path)

    result: dict[str, _typing.Any] = {
        "path": str(skill_path),
        "valid": False,
        "warnings": [],
        "error": None,
    }

    try:
        skill = skills.load_skill(skill_path)
        result["valid"] = True
        result["name"] = skill.name
        result["description"] = skill.description
        result["body_lines"] = skill.body_line_count

        if skill.exceeds_soft_limit:
            result["warnings"].append(
                f"Body exceeds recommended limit ({skill.body_line_count} > {skills.SKILL_BODY_SOFT_LIMIT} lines)"
            )
    except (FileNotFoundError, ValueError) as e:
        result["error"] = str(e)

    if json_output:
        _click.echo(_json.dumps(result, indent=2))
    else:
        _click.echo(f"Skill: {skill_path}")
        if result["error"]:
            _click.echo("  Status: ✗ invalid")
            _click.echo(f"  Error: {result['error']}")
        elif result["warnings"]:
            _click.echo("  Status: ⚠ valid with warnings")
            for warning in result["warnings"]:
                _click.echo(f"  Warning: {warning}")
        else:
            _click.echo("  Status: ✓ valid")
        if result.get("name"):
            _click.echo(f"  Name: {result['name']}")
            _click.echo(f"  Body lines: {result['body_lines']}")


# =============================================================================
# Profile Commands
# =============================================================================


@cli.group(name="profile")
def profile_group() -> None:
    """Model profile management commands."""
    pass


@profile_group.command(name="list")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
def profile_list(json_output: bool) -> None:
    """List all available model profiles."""
    import brynhild.profiles.manager as profiles_manager

    manager = profiles_manager.ProfileManager()

    profiles = manager.list_profiles()

    if json_output:
        _click.echo(_json.dumps({
            "profiles": [p.to_dict() for p in profiles],
            "count": len(profiles),
        }, indent=2))
    else:
        if not profiles:
            _click.echo("No profiles found.")
            return

        _click.echo(f"Model Profiles ({len(profiles)}):")
        _click.echo(f"{'Name':<25} {'Family':<15} {'Tools':<6} {'Reasoning'}")
        _click.echo("-" * 60)
        for p in profiles:
            tools = "✓" if p.supports_tools else "✗"
            reasoning = "✓" if p.supports_reasoning else "✗"
            _click.echo(f"{p.name:<25} {p.family:<15} {tools:<6} {reasoning}")


@profile_group.command(name="show")
@_click.argument("name")
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
def profile_show(name: str, json_output: bool) -> None:
    """Show details for a specific model profile."""
    import brynhild.profiles.manager as profiles_manager

    manager = profiles_manager.ProfileManager()
    profile = manager.get_profile(name)

    if profile is None:
        if json_output:
            _click.echo(_json.dumps({"error": f"Profile not found: {name}"}))
        else:
            _click.echo(f"Error: Profile '{name}' not found", err=True)
        raise SystemExit(1)

    if json_output:
        _click.echo(_json.dumps(profile.to_dict(), indent=2))
    else:
        _click.echo(f"Profile: {profile.name}")
        _click.echo(f"  Family: {profile.family or '(none)'}")
        _click.echo(f"  Description: {profile.description or '(none)'}")
        _click.echo()
        _click.echo("API Settings:")
        _click.echo(f"  Default temperature: {profile.default_temperature}")
        _click.echo(f"  Default max_tokens: {profile.default_max_tokens}")
        if profile.min_max_tokens:
            _click.echo(f"  Minimum max_tokens: {profile.min_max_tokens}")
        _click.echo()
        _click.echo("Capabilities:")
        _click.echo(f"  Supports tools: {'✓' if profile.supports_tools else '✗'}")
        _click.echo(f"  Supports reasoning: {'✓' if profile.supports_reasoning else '✗'}")
        _click.echo(f"  Supports streaming: {'✓' if profile.supports_streaming else '✗'}")
        _click.echo()
        _click.echo("Behavior:")
        _click.echo(f"  Eagerness: {profile.eagerness}")
        _click.echo(f"  Verbosity: {profile.verbosity}")
        _click.echo(f"  Thoroughness: {profile.thoroughness}")

        if profile.api_params:
            _click.echo()
            _click.echo("API Parameters:")
            for key, value in profile.api_params.items():
                _click.echo(f"  {key}: {value}")


@profile_group.command(name="resolve")
@_click.argument("model", required=False)
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
@_click.pass_context
def profile_resolve(
    ctx: _click.Context, model: str | None, json_output: bool
) -> None:
    """Resolve which profile would be used for a model.

    If MODEL is not specified, uses the configured model.
    """
    import brynhild.profiles.manager as profiles_manager

    settings: config.Settings = ctx.obj["settings"]
    manager = profiles_manager.ProfileManager()

    model_name = model or settings.model
    profile = manager.resolve(model_name, settings.provider)

    if json_output:
        _click.echo(_json.dumps({
            "model": model_name,
            "provider": settings.provider,
            "resolved_profile": profile.name,
            "profile": profile.to_dict(),
        }, indent=2))
    else:
        _click.echo(f"Model: {model_name}")
        _click.echo(f"Provider: {settings.provider}")
        _click.echo(f"Resolved Profile: {profile.name}")
        _click.echo()
        _click.echo("Profile Settings:")
        _click.echo(f"  Temperature: {profile.default_temperature}")
        _click.echo(f"  Max tokens: {profile.default_max_tokens}")
        _click.echo(f"  Supports tools: {'✓' if profile.supports_tools else '✗'}")


# =============================================================================
# Developer Commands (Hidden)
# =============================================================================

cli.add_command(cli_dev.dev_group)


def main() -> None:
    """Main entry point with correct program name."""
    cli(prog_name="brynhild")


if __name__ == "__main__":
    main()
