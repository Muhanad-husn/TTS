"""Audio device resolution and listing."""

import sys

import sounddevice as sd
from rich.table import Table

from read_aloud import console


def has_audio_output() -> bool:
    """Return True if at least one audio output device is available."""
    try:
        sd.query_devices(kind="output")
        return True
    except sd.PortAudioError:
        return False


def resolve_device(spec: str) -> int | str:
    """Resolve a device spec (index or name substring) to a device identifier."""
    try:
        return int(spec)
    except ValueError:
        pass
    # Search by name substring
    try:
        devices = sd.query_devices()
    except sd.PortAudioError:
        console.print("[red]Error: No audio devices available[/red]")
        sys.exit(1)
    spec_lower = spec.lower()
    for i, dev in enumerate(devices):
        if spec_lower in dev["name"].lower() and dev["max_output_channels"] > 0:
            return i
    console.print(f"[red]Error: No output device matching '{spec}'[/red]")
    sys.exit(1)


def list_devices() -> None:
    """Print a table of output audio devices."""
    try:
        devices = sd.query_devices()
    except sd.PortAudioError:
        console.print("[yellow]No audio devices available.[/yellow]")
        return
    table = Table(title="Audio Output Devices")
    table.add_column("Index", style="cyan", justify="right")
    table.add_column("Name", style="white")
    table.add_column("Channels", style="green", justify="right")
    table.add_column("Sample Rate", style="yellow", justify="right")
    default_out = sd.default.device[1]
    for i, dev in enumerate(devices):
        if dev["max_output_channels"] > 0:
            name = dev["name"]
            if i == default_out:
                name += " [bold green](default)[/bold green]"
            table.add_row(
                str(i), name,
                str(dev["max_output_channels"]),
                str(int(dev["default_samplerate"])),
            )
    console.print(table)
