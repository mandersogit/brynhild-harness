"""
Rich console renderer (Layer 3).

Outputs formatted text with colors, panels, and syntax highlighting
using the Rich library.
"""

import typing as _typing

import rich.console as _rich_console
import rich.live as _rich_live
import rich.markdown as _rich_markdown
import rich.panel as _rich_panel
import rich.prompt as _rich_prompt
import rich.syntax as _rich_syntax
import rich.text as _rich_text

import brynhild.ui.base as base


class RichConsoleRenderer(base.Renderer):
    """
    Rich console renderer with colors and formatting.

    Uses the Rich library for beautiful terminal output including:
    - Colored text and panels
    - Markdown rendering
    - Syntax highlighting
    - Live streaming updates
    """

    def __init__(
        self,
        console: _rich_console.Console | None = None,
        *,
        force_terminal: bool | None = None,
        no_color: bool = False,
    ) -> None:
        """
        Initialize the Rich renderer.

        Args:
            console: Rich Console instance (created if not provided).
            force_terminal: Force terminal mode even if not detected.
            no_color: Disable all colors.
        """
        self._console = console or _rich_console.Console(
            force_terminal=force_terminal,
            no_color=no_color,
        )
        self._streaming = False
        self._stream_content = ""
        self._live: _rich_live.Live | None = None

    def show_user_message(self, content: str) -> None:
        """Display a user message with formatting."""
        self._console.print(
            _rich_panel.Panel(
                content,
                title="[bold blue]You[/bold blue]",
                border_style="blue",
            )
        )

    def show_assistant_text(self, text: str, *, streaming: bool = False) -> None:
        """Display assistant text response."""
        if streaming:
            self._stream_content += text
            # Update display (whitespace filtering is done in RendererCallbacks)
            if self._live:
                self._live.update(
                    _rich_panel.Panel(
                        _rich_markdown.Markdown(self._stream_content),
                        title="[bold green]Assistant[/bold green]",
                        border_style="green",
                    )
                )
        else:
            if not self._streaming:
                # Complete message (non-streaming)
                self._console.print(
                    _rich_panel.Panel(
                        _rich_markdown.Markdown(text),
                        title="[bold green]Assistant[/bold green]",
                        border_style="green",
                    )
                )

    def show_tool_call(self, tool_call: base.ToolCallDisplay) -> None:
        """Display that a tool is being called."""
        # Format the input as a simple key-value display
        input_lines: list[str] = []
        for key, value in tool_call.tool_input.items():
            value_str = str(value)
            if len(value_str) > 100:
                value_str = value_str[:97] + "..."
            input_lines.append(f"[dim]{key}:[/dim] {value_str}")

        content = "\n".join(input_lines) if input_lines else "[dim]No parameters[/dim]"

        # Use different styling for recovered vs native tool calls
        if tool_call.is_recovered:
            # Prominent warning banner for recovered calls
            self._console.print(
                "[bold #ff8c00 on #3d2600]"
                " ⚠️  RECOVERED FROM MODEL THINKING "
                "[/bold #ff8c00 on #3d2600]"
            )
            self._console.print(
                "[dim #ff8c00]"
                "   Model emitted JSON in thinking instead of proper tool call"
                "[/dim #ff8c00]"
            )

            # Orange border with warning icon (extra space after ⚠️ to match ⚡ visually)
            title = f"[bold #ff8c00]⚠️  {tool_call.tool_name}[/bold #ff8c00]"
            subtitle = "[dim #ff8c00](recovered from model thinking)[/dim #ff8c00]"
            border_style = "#ff8c00"  # Orange
        else:
            # Yellow border and "⚡" for native calls
            title = f"[bold yellow]⚡ {tool_call.tool_name}[/bold yellow]"
            subtitle = None
            border_style = "yellow"

        self._console.print(
            _rich_panel.Panel(
                content,
                title=title,
                subtitle=subtitle,
                border_style=border_style,
            )
        )

    def show_tool_result(self, result: base.ToolResultDisplay) -> None:
        """Display the result of a tool call."""
        if result.result.success:
            output = result.result.output.strip()
            if len(output) > 2000:
                output = output[:1997] + "..."

            # Try to detect and syntax-highlight the output
            # For now, just use plain text - could add syntax detection later
            content: _rich_text.Text | _rich_syntax.Syntax | str = (
                output or "[dim]No output[/dim]"
            )

            self._console.print(
                _rich_panel.Panel(
                    content,
                    title=f"[bold green]✓ {result.tool_name}[/bold green]",
                    border_style="green",
                )
            )
        else:
            error_msg = result.result.error or "Unknown error"
            self._console.print(
                _rich_panel.Panel(
                    f"[red]{error_msg}[/red]",
                    title=f"[bold red]✗ {result.tool_name}[/bold red]",
                    border_style="red",
                )
            )

    def show_error(self, error: str) -> None:
        """Display an error message."""
        self._console.print(f"[bold red]Error:[/bold red] {error}")

    def show_info(self, message: str) -> None:
        """Display an informational message."""
        self._console.print(f"[dim]{message}[/dim]")

    def start_streaming(self) -> None:
        """Start live streaming display."""
        self._streaming = True
        self._stream_content = ""
        # Use transient=True so live display is cleared when stopped
        # We'll print the final panel separately if there's content
        self._live = _rich_live.Live(
            _rich_panel.Panel(
                "[dim]Thinking...[/dim]",
                title="[bold green]Assistant[/bold green]",
                border_style="green",
            ),
            console=self._console,
            refresh_per_second=10,
            transient=True,
        )
        self._live.start()

    def end_streaming(self) -> None:
        """End live streaming display."""
        if self._live:
            # Stop the live display (transient=True clears it)
            self._live.stop()
            self._live = None

            # Print final panel if we have content
            # (Whitespace filtering is done in RendererCallbacks)
            if self._stream_content:
                self._console.print(
                    _rich_panel.Panel(
                        _rich_markdown.Markdown(self._stream_content),
                        title="[bold green]Assistant[/bold green]",
                        border_style="green",
                    )
                )

        self._streaming = False
        self._stream_content = ""

    def prompt_permission(
        self,
        tool_call: base.ToolCallDisplay,
        *,
        auto_approve: bool = False,
    ) -> bool:
        """Ask user for permission to execute a tool."""
        if auto_approve:
            return True

        # Tool call is already displayed by caller, just prompt
        return _rich_prompt.Confirm.ask(
            f"[yellow]Allow {tool_call.tool_name}?[/yellow]",
            console=self._console,
            default=False,
        )

    def finalize(self, result: dict[str, _typing.Any] | None = None) -> None:
        """Finalize output - show usage stats if available."""
        if result and "usage" in result:
            usage = result["usage"]
            self._console.print(
                f"\n[dim]Tokens: {usage.get('input_tokens', 0)} in / "
                f"{usage.get('output_tokens', 0)} out[/dim]"
            )

