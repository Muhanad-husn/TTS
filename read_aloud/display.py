"""Rich display helpers for live status and dry-run output."""

import time

from rich.panel import Panel
from rich.text import Text

from read_aloud import console
from read_aloud.models import PlaybackState


def _format_time(seconds: float) -> str:
    """Format seconds as M:SS or H:MM:SS."""
    if seconds < 0:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _build_status_display(state: PlaybackState, interactive: bool) -> Text:
    """Build a rich Text renderable for the live status line."""
    elapsed = time.monotonic() - state.start_time if state.start_time else 0

    # Estimate remaining
    if state.completed_count > 0:
        avg = elapsed / state.completed_count
        remaining = avg * (state.total - state.completed_count)
    else:
        remaining = -1

    parts = []
    parts.append(f"[bold cyan][{state.current_index}/{state.total}][/bold cyan]")
    parts.append(f"  Elapsed: [green]{_format_time(elapsed)}[/green]")
    parts.append(f"  Remaining: [yellow]{_format_time(remaining)}[/yellow]")

    if state.paused:
        parts.append("  [bold red][PAUSED][/bold red]")

    line = "".join(parts)

    if state.current_preview:
        line += f"\n  [dim]{state.current_preview}[/dim]"

    if interactive:
        line += "\n  [dim]\\[space] pause  \\[n] next  \\[q] quit[/dim]"

    return Text.from_markup(line)


def display_dry_run(paragraphs: list[str]) -> None:
    """Display parsed paragraphs without connecting to the server."""
    lines = []
    total_chars = 0
    for i, para in enumerate(paragraphs, 1):
        total_chars += len(para)
        preview = para[:120] + ("..." if len(para) > 120 else "")
        lines.append(f"[bold cyan]{i:>4}.[/bold cyan] {preview}")

    body = "\n".join(lines)
    console.print(Panel(
        body,
        title=f"[bold]Dry Run \u2014 {len(paragraphs)} paragraphs, {total_chars:,} characters[/bold]",
        border_style="dim",
    ))
