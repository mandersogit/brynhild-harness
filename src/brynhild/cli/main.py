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
import brynhild.config as config
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
@_click.pass_context
def cli(
    ctx: _click.Context,
    print_mode: bool,
    json_output: bool,
    provider: str | None,
    model: str | None,
    verbose: bool,
    resume: str | None,
    profile: str | None,
    dangerously_skip_permissions: bool,
    dangerously_skip_sandbox: bool,
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
    ctx.obj["profile_name"] = profile

    # If a subcommand is invoked, let it handle everything
    if ctx.invoked_subcommand is not None:
        return

    # No subcommand - show help or start interactive mode
    if print_mode:
        _click.echo("Error: Use 'brynhild chat -p \"prompt\"' for print mode", err=True)
        raise SystemExit(1)
    else:
        # Interactive mode with profile support
        _handle_interactive_mode(settings, profile_name=profile)


def _create_renderer(
    json_output: bool,
    no_color: bool,
) -> ui.Renderer:
    """Create the appropriate renderer based on output mode."""
    if json_output:
        return ui.JSONRenderer()
    elif no_color or not _sys.stdout.isatty():
        return ui.PlainTextRenderer()
    else:
        return ui.RichConsoleRenderer()


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
    log_file: str | None = None,
    profile_name: str | None = None,
) -> None:
    """Run a conversation using the ConversationRunner."""
    import brynhild.core as core

    # Create renderer
    renderer = _create_renderer(json_output, no_color)

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

    if verbose and context.injections:
        renderer.show_info(f"Applied {len(context.injections)} context injection(s)")
        if context.profile:
            renderer.show_info(f"Using profile: {context.profile.name}")

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
        system_prompt=context.system_prompt,  # Use enhanced prompt
    )

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
        if json_output:
            renderer.finalize()
        raise SystemExit(1) from None

    finally:
        # Close the logger
        if conv_logger:
            conv_logger.close()


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


def _handle_interactive_mode(
    settings: config.Settings,
    profile_name: str | None = None,
) -> None:
    """Handle interactive TUI mode."""
    import brynhild.core as core

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
@_click.option("--log-file", type=str, default=None, help="Explicit log file path")
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
    log_file: str | None,
    prompt: tuple[str, ...],
) -> None:
    """Send a prompt to the AI (single query mode)."""
    settings: config.Settings = ctx.obj["settings"]

    # Note: print_mode is accepted but not currently used - JSON output is primary
    _ = print_mode  # Acknowledge the parameter

    # Handle prompt from arguments or stdin
    prompt_text = " ".join(prompt) if prompt else None

    # Check for piped input
    if not prompt_text and not _sys.stdin.isatty():
        prompt_text = _sys.stdin.read().strip()

    if not prompt_text:
        if json_output:
            _click.echo(_json.dumps({"error": "No prompt provided"}, indent=2))
        else:
            _click.echo(
                'Error: No prompt provided. Usage: brynhild chat "your prompt"',
                err=True,
            )
        raise SystemExit(1)

    # Get profile from parent context
    profile_name: str | None = ctx.obj.get("profile_name")

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
            profile_name=profile_name,
        )
    )


@cli.command()
@_click.option("--json", "json_output", is_flag=True, help="JSON output")
@_click.pass_context
def config_cmd(ctx: _click.Context, json_output: bool) -> None:
    """Show current configuration."""
    settings: config.Settings = ctx.obj["settings"]

    if json_output:
        _click.echo(_json.dumps(settings.to_dict(), indent=2))
    else:
        _click.echo("Brynhild Configuration:")
        _click.echo(f"  Provider: {settings.provider}")
        _click.echo(f"  Model: {settings.model}")
        _click.echo(f"  Max Tokens: {settings.max_tokens}")
        _click.echo(f"  API Key: {'✓ configured' if settings.get_api_key() else '✗ missing'}")
        _click.echo(f"  Project Root: {settings.project_root}")
        _click.echo(f"  Config Dir: {settings.config_dir}")
        _click.echo(f"  Sessions Dir: {settings.sessions_dir}")


# Register config_cmd with the name "config" to avoid shadowing the module
cli.add_command(config_cmd, name="config")


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
def tools_list(json_output: bool) -> None:
    """List all available tools."""
    registry = _get_tool_registry()

    if json_output:
        tool_list = [
            {
                "name": t.name,
                "description": t.description,
            }
            for t in registry.list_tools()
        ]
        _click.echo(_json.dumps(tool_list, indent=2))
    else:
        _click.echo("Available Tools:")
        for t in registry.list_tools():
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

    # Find all log files
    log_files = sorted(log_dir.glob("brynhild_*.jsonl"), reverse=True)[:limit]

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
    log_dir = settings.logs_dir

    # Determine which file to view
    if log_file:
        log_path = _pathlib.Path(log_file)
        if not log_path.is_absolute():
            log_path = log_dir / log_file
    else:
        # Find most recent
        log_files = sorted(log_dir.glob("brynhild_*.jsonl"), reverse=True)
        if not log_files:
            _click.echo(f"No logs found in {log_dir}", err=True)
            raise SystemExit(1)
        log_path = log_files[0]

    if not log_path.exists():
        _click.echo(f"Log file not found: {log_path}", err=True)
        raise SystemExit(1)

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

        elif event_type == "session_end":
            _click.echo(f"🏁 Session ended ({event.get('total_events', 0)} events)")
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
    import brynhild.skills as skills

    settings: config.Settings = ctx.obj["settings"]
    registry = skills.SkillRegistry(project_root=settings.project_root)

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
    import brynhild.skills as skills

    settings: config.Settings = ctx.obj["settings"]
    registry = skills.SkillRegistry(project_root=settings.project_root)

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


def main() -> None:
    """Main entry point with correct program name."""
    cli(prog_name="brynhild")


if __name__ == "__main__":
    main()
