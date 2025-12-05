"""
Markdown logger for Brynhild.

Generates presentation-grade markdown output from conversation events.
This output is suitable for sharing as a professional work product.
"""

import datetime as _datetime
import json as _json
import pathlib as _pathlib
import typing as _typing


def format_markdown_table(
    headers: list[str],
    rows: list[list[str]],
) -> str:
    """
    Format a properly aligned markdown table.

    Args:
        headers: Column header strings.
        rows: List of rows, each row is a list of cell values.

    Returns:
        Formatted markdown table string with aligned columns.

    Example:
        >>> format_markdown_table(
        ...     ["Name", "Value"],
        ...     [["Total", "100"], ["Average", "25"]],
        ... )
        '| Name    | Value |\\n|---------|-------|\\n| Total   | 100   |\\n| Average | 25    |\\n'
    """
    if not headers or not rows:
        return ""

    # Calculate column widths (max of header and all row values)
    num_cols = len(headers)
    widths = [len(h) for h in headers]

    for row in rows:
        for i, cell in enumerate(row[:num_cols]):
            widths[i] = max(widths[i], len(cell))

    # Build table
    lines: list[str] = []

    # Header row
    header_cells = [f" {headers[i]:<{widths[i]}} " for i in range(num_cols)]
    lines.append("|" + "|".join(header_cells) + "|")

    # Separator row
    sep_cells = ["-" * (widths[i] + 2) for i in range(num_cols)]
    lines.append("|" + "|".join(sep_cells) + "|")

    # Data rows
    for row in rows:
        data_cells = [f" {row[i] if i < len(row) else '':<{widths[i]}} " for i in range(num_cols)]
        lines.append("|" + "|".join(data_cells) + "|")

    return "\n".join(lines) + "\n"


class MarkdownLogger:
    """
    Generates presentation-grade markdown from conversation events.

    Unlike ConversationLogger (JSONL for machines), this produces
    human-readable markdown suitable for documentation and sharing.

    The markdown is accumulated in memory and written when close() is called.
    This ensures clean, well-structured output even if events arrive
    out of order or need post-processing.

    Usage:
        logger = MarkdownLogger(
            output_path=Path("session.md"),
            provider="openrouter",
            model="anthropic/claude-sonnet-4",
        )
        logger.log_session_start("20251205_143022")
        logger.log_user_message("Hello")
        logger.log_assistant_message("Hi there!")
        logger.close()  # Writes the markdown file
    """

    def __init__(
        self,
        output_path: _pathlib.Path | str,
        *,
        title: str | None = None,
        provider: str = "",
        model: str = "",
        profile: str | None = None,
        include_thinking: bool = True,
        thinking_style: str = "collapsible",
        truncate_tool_output: int = 2000,
    ) -> None:
        """
        Initialize the markdown logger.

        Args:
            output_path: Path for the output markdown file.
            title: Title for the document (default: timestamp).
            provider: LLM provider name.
            model: Model name.
            profile: Profile name (if any).
            include_thinking: Whether to include thinking sections.
            thinking_style: How to render thinking:
                - "collapsible": Use <details> tags
                - "full": Show full content
                - "summary": Show word count only
                - "hidden": Don't show at all
            truncate_tool_output: Max chars for tool output (0 = no limit).
        """
        self._output_path = _pathlib.Path(output_path)
        self._title = title
        self._provider = provider
        self._model = model
        self._profile = profile
        self._include_thinking = include_thinking
        self._thinking_style = thinking_style
        self._truncate_tool_output = truncate_tool_output

        # Session metadata
        self._session_id: str = ""
        self._start_time: _datetime.datetime | None = None

        # Accumulated content
        self._sections: list[str] = []

        # Usage tracking for summary
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost: float = 0.0
        self._tools_used: dict[str, int] = {}  # tool_name -> call_count
        self._tool_recoveries = 0  # Count of tool calls recovered from thinking

        # State tracking
        self._last_thinking: str | None = None  # Buffer for thinking before assistant message
        self._pending_usage: list[tuple[int, int, float | None]] = []  # Buffer usage until turn ends
        self._enabled = True

    def log_session_start(self, session_id: str) -> None:
        """Log session start - initializes header metadata."""
        self._session_id = session_id
        self._start_time = _datetime.datetime.now()

    def log_system_prompt(self, content: str) -> None:
        """Log system prompt (optional - usually not shown in presentation output)."""
        # System prompt is typically not included in presentation markdown
        # but we could add it as an appendix if needed
        pass

    def log_user_message(self, content: str) -> None:
        """Log a user message."""
        # Flush any buffered thinking first (shouldn't happen but be safe)
        self._flush_thinking()
        # Flush any pending usage from the previous assistant turn
        self._flush_pending_usage()

        self._sections.append(f"### User\n\n{content}\n")

    def log_assistant_message(
        self,
        content: str,
        thinking: str | None = None,
    ) -> None:
        """Log an assistant message with optional thinking."""
        # Use provided thinking or buffered thinking
        thinking_to_use = thinking or self._last_thinking
        self._last_thinking = None

        section = "### Assistant\n\n"

        # Add content
        if content:
            section += f"{content}\n"

        # Add thinking if enabled and available
        if thinking_to_use and self._include_thinking:
            section += "\n" + self._format_thinking(thinking_to_use)

        self._sections.append(section)

    def log_thinking(self, content: str) -> None:
        """Log reasoning/thinking trace - buffers until assistant message."""
        # Buffer thinking to attach to next assistant message
        if self._last_thinking:
            self._last_thinking += "\n" + content
        else:
            self._last_thinking = content

    def log_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, _typing.Any],
        tool_id: str | None = None,  # noqa: ARG002
    ) -> None:
        """Log a tool call request."""
        # Flush any buffered thinking
        self._flush_thinking()

        # Track tool usage
        self._tools_used[tool_name] = self._tools_used.get(tool_name, 0) + 1

        # Format input JSON
        try:
            input_json = _json.dumps(tool_input, indent=2, default=str)
        except (TypeError, ValueError):
            input_json = str(tool_input)

        # Truncate if needed
        if self._truncate_tool_output and len(input_json) > self._truncate_tool_output:
            input_json = input_json[:self._truncate_tool_output] + "\n... [truncated]"

        section = f"### 🔧 Tool: {tool_name}\n\n"
        section += "**Input:**\n"
        section += f"```json\n{input_json}\n```\n"

        self._sections.append(section)

    def log_tool_result(
        self,
        tool_name: str,  # noqa: ARG002 - kept for API compatibility
        success: bool,
        output: str | None = None,
        error: str | None = None,
        tool_id: str | None = None,  # noqa: ARG002
    ) -> None:
        """Log a tool execution result."""
        if success:
            icon = "✅"
            status = "Success"
            content = output or "(no output)"
        else:
            icon = "❌"
            status = "Failed"
            content = error or output or "(no details)"

        # Truncate if needed
        if self._truncate_tool_output and len(content) > self._truncate_tool_output:
            content = content[:self._truncate_tool_output] + "\n... [truncated]"

        section = f"**Output:** {icon} {status}\n"

        # Format output nicely
        if content and content.strip():
            # Check if it looks like code or structured output
            if "\n" in content or len(content) > 100:
                section += f"```\n{content}\n```\n"
            else:
                section += f"`{content}`\n"

        self._sections.append(section)

    def log_error(self, error: str, context: str | None = None) -> None:
        """Log an error event."""
        section = "### ❌ Error\n\n"
        section += f"**Error:** {error}\n"
        if context:
            section += f"\n**Context:** {context}\n"
        self._sections.append(section)

    def log_finish(
        self,
        status: str,
        summary: str,
        next_steps: str | None = None,
    ) -> None:
        """Log task completion (Finish tool result)."""
        # Determine icon based on status
        status_icons = {
            "success": "✅",
            "partial": "⚠️",
            "failed": "❌",
            "blocked": "🚫",
        }
        icon = status_icons.get(status.lower(), "ℹ️")

        section = f"### {icon} Task Complete\n\n"
        section += f"**Status:** {status.capitalize()}\n\n"
        section += f"**Summary:** {summary}\n"

        if next_steps:
            section += f"\n**Next Steps:**\n{next_steps}\n"

        self._sections.append(section)

    def log_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        *,
        cost: float | None = None,
        reasoning_tokens: int | None = None,  # noqa: ARG002
    ) -> None:
        """Log token usage - flushes previous usage, buffers new one."""
        # A new usage event means a new API call completed.
        # Flush any PREVIOUS buffered usage to the last section (content from previous API call)
        self._flush_pending_usage()

        # Buffer this new usage - it will be flushed when next API call completes or turn ends
        self._pending_usage.append((input_tokens, output_tokens, cost))

        # Accumulate for summary
        self._total_input_tokens = input_tokens  # Use latest (context size)
        self._total_output_tokens += output_tokens  # Accumulate output
        if cost is not None:
            self._total_cost += cost

    def _flush_pending_usage(self) -> None:
        """Flush any pending usage to the last section."""
        if not self._pending_usage or not self._sections:
            self._pending_usage = []
            return

        # Add all buffered usage entries as footers to the last section
        for input_tokens, output_tokens, cost in self._pending_usage:
            usage_line = f"\n*Context: {input_tokens:,} tokens | Generated: {output_tokens:,} tokens"
            if cost is not None and cost > 0:
                usage_line += f" | ${cost:.4f}"
            usage_line += "*\n"
            self._sections[-1] += usage_line

        self._pending_usage = []

    def log_event(self, event_type: str, **kwargs: _typing.Any) -> None:  # noqa: ARG002
        """Log a generic event - most are not shown in presentation output."""
        # Track tool recoveries for summary
        if event_type == "tool_call_recovered":
            self._tool_recoveries += 1

    def _format_thinking(self, thinking: str) -> str:
        """Format thinking content according to configured style."""
        if not thinking or self._thinking_style == "hidden":
            return ""

        word_count = len(thinking.split())

        if self._thinking_style == "summary":
            return f"*💭 Thinking ({word_count} words)*\n"

        elif self._thinking_style == "collapsible":
            return f"""<details>
<summary>💭 Thinking ({word_count} words)</summary>

{thinking}

</details>
"""

        else:  # "full"
            return f"#### 💭 Thinking\n\n{thinking}\n"

    def _flush_thinking(self) -> None:
        """Flush any buffered thinking as a standalone section."""
        if self._last_thinking and self._include_thinking:
            section = self._format_thinking(self._last_thinking)
            if section:
                self._sections.append(section)
        self._last_thinking = None

    def _render_header(self) -> str:
        """Render the document header."""
        # Determine title
        if self._title:
            title = self._title
        elif self._session_id:
            title = f"Session {self._session_id}"
        else:
            title = "Brynhild Session"

        # Format date
        if self._start_time:
            date_str = self._start_time.strftime("%B %d, %Y at %I:%M %p")
        else:
            date_str = _datetime.datetime.now().strftime("%B %d, %Y at %I:%M %p")

        header = f"# Brynhild Session: {title}\n\n"
        header += f"> **Model**: {self._model}  \n"
        header += f"> **Provider**: {self._provider}  \n"
        header += f"> **Profile**: {self._profile or 'default'}  \n"
        header += f"> **Date**: {date_str}  \n"
        if self._session_id:
            header += f"> **Session ID**: {self._session_id}\n"
        header += "\n---\n\n## Conversation\n\n"

        return header

    def _render_summary(self) -> str:
        """Render the session summary footer."""
        rows: list[list[str]] = []

        # Context size (input tokens)
        if self._total_input_tokens > 0:
            rows.append(["Context Size", f"{self._total_input_tokens:,} tokens"])

        # Generated tokens
        if self._total_output_tokens > 0:
            rows.append(["Generated", f"{self._total_output_tokens:,} tokens"])

        # Cost (if tracked)
        if self._total_cost > 0:
            rows.append(["Estimated Cost", f"${self._total_cost:.4f}"])

        # Tools used
        if self._tools_used:
            tools_str = ", ".join(
                f"{name} ({count})" for name, count in sorted(self._tools_used.items())
            )
            rows.append(["Tools Used", tools_str])

        # Tool recoveries (if any)
        if self._tool_recoveries > 0:
            rows.append(["Tool Recoveries", str(self._tool_recoveries)])

        # Duration
        if self._start_time:
            duration = _datetime.datetime.now() - self._start_time
            duration_str = str(duration).split(".")[0]  # Remove microseconds
            rows.append(["Duration", duration_str])

        summary = "\n---\n\n## Session Summary\n\n"
        summary += format_markdown_table(["Metric", "Value"], rows)

        return summary

    def _render_document(self) -> str:
        """Render the complete markdown document."""
        parts = [
            self._render_header(),
            *self._sections,
            self._render_summary(),
        ]
        return "\n".join(parts)

    @property
    def output_path(self) -> _pathlib.Path:
        """Get the output file path."""
        return self._output_path

    @property
    def enabled(self) -> bool:
        """Check if logging is enabled."""
        return self._enabled

    def close(self) -> None:
        """Write the markdown file and close the logger."""
        if not self._enabled:
            return

        # Flush any remaining buffered content
        self._flush_thinking()
        self._flush_pending_usage()

        # Render and write
        document = self._render_document()

        # Ensure parent directory exists
        self._output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the file
        try:
            self._output_path.write_text(document, encoding="utf-8")
        except OSError as e:
            # Log error but don't crash
            import sys as _sys
            print(f"Warning: Failed to write markdown output: {e}", file=_sys.stderr)

        self._enabled = False

    def __enter__(self) -> "MarkdownLogger":
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


def export_log_to_markdown(
    events: list[dict[str, _typing.Any]],
    *,
    title: str | None = None,
    include_thinking: bool = True,
    thinking_style: str = "collapsible",
    truncate_tool_output: int = 2000,
) -> str:
    """
    Generate presentation markdown from JSONL log events.

    This is a standalone function for generating markdown from existing logs,
    used by `brynhild logs export` command.

    Args:
        events: List of event dictionaries from JSONL log.
        title: Title for the document (default: uses session_id from log).
        include_thinking: Whether to include thinking sections.
        thinking_style: How to render thinking (collapsible, full, summary, hidden).
        truncate_tool_output: Max chars for tool output (0 = no limit).

    Returns:
        Complete markdown document as string.
    """
    # Extract session info from events
    session_id = ""
    provider = ""
    model = ""
    start_time: str | None = None

    for event in events:
        if event.get("event_type") == "session_start":
            session_id = event.get("session_id", "")
            provider = event.get("provider", "")
            model = event.get("model", "")
            start_time = event.get("timestamp")
            break

    # Build markdown sections
    sections: list[str] = []
    tools_used: dict[str, int] = {}
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost: float = 0.0
    tool_recoveries = 0
    last_thinking: str | None = None
    pending_usage: list[tuple[int, int, float]] = []  # Buffer usage until turn ends

    def flush_pending_usage() -> None:
        """Flush pending usage to the last section."""
        nonlocal pending_usage
        if not pending_usage or not sections:
            pending_usage = []
            return
        for input_tok, output_tok, cost in pending_usage:
            usage_line = f"\n*Context: {input_tok:,} tokens | Generated: {output_tok:,} tokens"
            if cost and cost > 0:
                usage_line += f" | ${cost:.4f}"
            usage_line += "*\n"
            sections[-1] += usage_line
        pending_usage = []

    def format_thinking(thinking: str) -> str:
        """Format thinking content according to style."""
        if not thinking or thinking_style == "hidden":
            return ""
        word_count = len(thinking.split())
        if thinking_style == "summary":
            return f"*💭 Thinking ({word_count} words)*\n"
        elif thinking_style == "collapsible":
            return f"""<details>
<summary>💭 Thinking ({word_count} words)</summary>

{thinking}

</details>
"""
        else:  # full
            return f"#### 💭 Thinking\n\n{thinking}\n"

    def truncate(text: str, max_len: int) -> str:
        """Truncate text if needed."""
        if max_len and len(text) > max_len:
            return text[:max_len] + "\n... [truncated]"
        return text

    # Process events
    for event in events:
        event_type = event.get("event_type")

        if event_type == "user_message":
            # Flush pending usage from previous assistant turn
            flush_pending_usage()
            content = event.get("content", "")
            sections.append(f"### User\n\n{content}\n")

        elif event_type == "assistant_message":
            content = event.get("content", "")
            thinking = event.get("thinking") or last_thinking
            last_thinking = None

            # Skip assistant messages that are just raw Finish tool JSON
            # Some models emit tool call arguments as literal text
            if content:
                content_stripped = content.strip()
                if (
                    content_stripped.startswith('{"status"')
                    and '"summary"' in content_stripped
                    and content_stripped.endswith("}")
                ):
                    # This is Finish tool JSON, skip it (we render Finish separately)
                    continue

            section = "### Assistant\n\n"
            if content:
                section += f"{content}\n"
            if thinking and include_thinking:
                section += "\n" + format_thinking(thinking)
            sections.append(section)

        elif event_type == "thinking":
            # Buffer thinking for next assistant message
            thinking_content = event.get("content", "")
            if last_thinking:
                last_thinking += "\n" + thinking_content
            else:
                last_thinking = thinking_content

        elif event_type == "tool_call":
            tool_name = event.get("tool_name", "Unknown")
            tool_input = event.get("tool_input", {})

            # Handle Finish tool specially - render as completion section
            if tool_name == "Finish":
                status = tool_input.get("status", "success")
                summary = tool_input.get("summary", "Task completed.")
                next_steps = tool_input.get("next_steps")

                status_icons = {
                    "success": "✅",
                    "partial": "⚠️",
                    "failed": "❌",
                    "blocked": "🚫",
                }
                icon = status_icons.get(status.lower(), "ℹ️")

                section = f"### {icon} Task Complete\n\n"
                section += f"**Status:** {status.capitalize()}\n\n"
                section += f"**Summary:** {summary}\n"
                if next_steps:
                    section += f"\n**Next Steps:**\n{next_steps}\n"
                sections.append(section)
                continue

            # Track tool usage
            tools_used[tool_name] = tools_used.get(tool_name, 0) + 1

            # Format input
            try:
                input_json = _json.dumps(tool_input, indent=2, default=str)
            except (TypeError, ValueError):
                input_json = str(tool_input)
            input_json = truncate(input_json, truncate_tool_output)

            section = f"### 🔧 Tool: {tool_name}\n\n"
            section += "**Input:**\n"
            section += f"```json\n{input_json}\n```\n"
            sections.append(section)

        elif event_type == "tool_result":
            # Skip Finish tool results (already rendered above)
            if event.get("tool_name") == "Finish":
                continue

            success = event.get("success", False)
            output = event.get("output", "")
            error = event.get("error", "")

            if success:
                icon = "✅"
                status = "Success"
                content = output or "(no output)"
            else:
                icon = "❌"
                status = "Failed"
                content = error or output or "(no details)"

            content = truncate(content, truncate_tool_output)

            section = f"**Output:** {icon} {status}\n"
            if content and content.strip():
                if "\n" in content or len(content) > 100:
                    section += f"```\n{content}\n```\n"
                else:
                    section += f"`{content}`\n"
            sections.append(section)

        elif event_type == "error":
            error = event.get("error", "Unknown error")
            context = event.get("context")
            section = "### ❌ Error\n\n"
            section += f"**Error:** {error}\n"
            if context:
                section += f"\n**Context:** {context}\n"
            sections.append(section)

        elif event_type == "usage":
            input_tokens = event.get("input_tokens", 0)
            output_tokens = event.get("output_tokens", 0)
            cost = event.get("cost_usd", 0)

            # A new usage event means a new API call completed.
            # Flush any PREVIOUS buffered usage to the last section (content from previous API call)
            flush_pending_usage()

            # Buffer this new usage - it will be flushed when next API call completes or turn ends
            pending_usage.append((input_tokens, output_tokens, cost))

            # Accumulate for summary
            total_input_tokens = input_tokens
            total_output_tokens += output_tokens
            if cost:
                total_cost += cost

        elif event_type == "tool_call_recovered":
            tool_recoveries += 1

    # Flush any remaining usage from the last turn
    flush_pending_usage()

    # Build header
    doc_title = title or f"Session {session_id}" if session_id else "Brynhild Session"
    if start_time:
        try:
            dt = _datetime.datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            date_str = dt.strftime("%B %d, %Y at %I:%M %p")
        except (ValueError, AttributeError):
            date_str = start_time[:19]
    else:
        date_str = "Unknown"

    header = f"# Brynhild Session: {doc_title}\n\n"
    header += f"> **Model**: {model}  \n"
    header += f"> **Provider**: {provider}  \n"
    header += f"> **Date**: {date_str}  \n"
    if session_id:
        header += f"> **Session ID**: {session_id}\n"
    header += "\n---\n\n## Conversation\n\n"

    # Build summary rows
    summary_rows: list[list[str]] = []

    # Context size (input tokens)
    if total_input_tokens > 0:
        summary_rows.append(["Context Size", f"{total_input_tokens:,} tokens"])

    # Generated tokens
    if total_output_tokens > 0:
        summary_rows.append(["Generated", f"{total_output_tokens:,} tokens"])

    # Cost
    if total_cost > 0:
        summary_rows.append(["Estimated Cost", f"${total_cost:.4f}"])

    # Tools used
    if tools_used:
        tools_str = ", ".join(f"{name} ({count})" for name, count in sorted(tools_used.items()))
        summary_rows.append(["Tools Used", tools_str])

    # Tool recoveries
    if tool_recoveries > 0:
        summary_rows.append(["Tool Recoveries", str(tool_recoveries)])

    summary = "\n---\n\n## Session Summary\n\n"
    summary += format_markdown_table(["Metric", "Value"], summary_rows)

    # Combine all parts
    return header + "\n".join(sections) + summary

