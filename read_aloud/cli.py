"""CLI entry point and main orchestrator."""

import argparse
import asyncio
import logging
import sys
import wave
from pathlib import Path

from rich.logging import RichHandler

from read_aloud import DEFAULT_URI, VOICES, console
from read_aloud.audio import has_audio_output, list_devices, resolve_device
from read_aloud.config import load_config, save_config
from read_aloud.display import display_dry_run
from read_aloud.keyboard import KeyboardListener
from read_aloud.models import SynthesisResult
from read_aloud.parsers import PARSERS, parse_page_ranges, split_long_paragraphs
from read_aloud.pipeline import _player_task, _synthesizer_task
from read_aloud.tts import list_server_voices, wait_for_server

try:
    import sounddevice as sd
    _HAS_SD = True
except (ImportError, OSError):
    _HAS_SD = False


async def read_aloud(
    file_path: Path,
    voice: str,
    uri: str,
    output: Path | None,
    dry_run: bool = False,
    pages: set[int] | None = None,
    start: int | None = None,
    end: int | None = None,
    device: int | str | None = None,
) -> None:
    """Parse a document and read it aloud paragraph by paragraph.

    Uses a producer-consumer pipeline so synthesis of paragraph N+1 overlaps
    with playback of paragraph N, eliminating dead air between paragraphs.
    """
    suffix = file_path.suffix.lower()
    parser = PARSERS.get(suffix)
    if parser is None:
        console.print(f"[red]Error: Unsupported file type '{suffix}'[/red]")
        console.print(f"[dim]Supported types: {', '.join(PARSERS)}[/dim]")
        sys.exit(1)

    if pages is not None and suffix != ".pdf":
        console.print("[red]Error: --pages is only supported for PDF files[/red]")
        sys.exit(1)

    console.print(f"[bold]Parsing[/bold] {file_path.name}...")
    paragraphs = parser(file_path, pages=pages)
    if not paragraphs:
        console.print("[yellow]No text found in file.[/yellow]")
        return

    paragraphs = split_long_paragraphs(paragraphs)

    # Apply --start / --end slicing
    total_before_slice = len(paragraphs)
    if start is not None or end is not None:
        s = (start - 1) if start is not None else 0
        e = end if end is not None else total_before_slice
        paragraphs = paragraphs[s:e]
        console.print(
            f"[dim]Reading paragraphs {s + 1}\u2013"
            f"{min(e, total_before_slice)} of {total_before_slice}[/dim]"
        )

    total = len(paragraphs)
    console.print(
        f"[bold cyan]Found {total} paragraph(s).[/bold cyan] "
        f"Voice: [green]{voice}[/green]\n"
    )

    if dry_run:
        display_dry_run(paragraphs)
        return

    await wait_for_server(uri)

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[SynthesisResult | None] = asyncio.Queue(maxsize=2)

    # Set up keyboard listener
    keyboard = KeyboardListener(loop)
    keyboard.start()

    synth = asyncio.create_task(_synthesizer_task(uri, paragraphs, voice, queue))
    all_pcm, audio_format = await _player_task(
        queue, loop, device=device, keyboard=keyboard
    )

    # If quit was requested, cancel the synthesizer
    if keyboard.quit_event.is_set():
        synth.cancel()
        try:
            await synth
        except asyncio.CancelledError:
            pass
    else:
        await synth

    console.print()

    if not all_pcm or audio_format is None:
        console.print("[yellow]No audio was synthesized.[/yellow]")
        return

    # Save to WAV
    save_path = output
    if save_path is None:
        try:
            answer = console.input(
                "[bold]Save audio as WAV?[/bold] [dim]\\[y/N][/dim] "
            ).strip().lower()
        except EOFError:
            answer = "n"
        if answer in ("y", "yes"):
            default_name = file_path.stem + ".wav"
            try:
                name = console.input(
                    f"[bold]Filename[/bold] [dim]\\[{default_name}][/dim]: "
                ).strip() or default_name
            except EOFError:
                name = default_name
            save_path = Path(name)

    if save_path is not None:
        rate, width, ch = audio_format
        combined = b"".join(all_pcm)
        with wave.open(str(save_path), "wb") as wf:
            wf.setnchannels(ch)
            wf.setsampwidth(width)
            wf.setframerate(rate)
            wf.writeframes(combined)
        console.print(
            f"[green]Saved:[/green] {save_path} "
            f"({len(combined) / (rate * width * ch):.1f}s)"
        )


def main() -> None:
    # Load config defaults
    config = load_config()

    parser = argparse.ArgumentParser(
        description="Read PDF, DOCX, EPUB, and Markdown files aloud "
                    "via Pocket-TTS Wyoming server"
    )
    parser.add_argument(
        "files", type=Path, nargs="*",
        help="Document(s) to read aloud",
    )
    parser.add_argument(
        "--voice", "-v",
        default="alba",
        choices=VOICES,
        help="TTS voice (default: alba)",
    )
    parser.add_argument(
        "--uri", "-u",
        default=DEFAULT_URI,
        help=f"Wyoming server URI (default: {DEFAULT_URI})",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Save WAV to this path (skips interactive prompt)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and display paragraphs without playing audio",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List audio output devices and exit",
    )
    parser.add_argument(
        "--device", "-d",
        default=None,
        help="Audio output device (index or name substring)",
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="Query server for available voices and exit",
    )
    parser.add_argument(
        "--pages",
        default=None,
        help="Page range for PDFs (e.g., '1-5,8,10-12')",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=None,
        help="Start at paragraph N (1-indexed)",
    )
    parser.add_argument(
        "--end",
        type=int,
        default=None,
        help="End at paragraph N (1-indexed)",
    )
    parser.add_argument(
        "--save-config",
        action="store_true",
        help="Save current flags as defaults to ~/.read_aloud.toml",
    )

    # Apply config defaults
    if config:
        parser.set_defaults(**config)

    args = parser.parse_args()

    # Configure logging with RichHandler
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )

    # Early-exit commands
    if args.list_devices:
        list_devices()
        return

    if args.list_voices:
        asyncio.run(list_server_voices(args.uri))
        return

    if args.save_config:
        save_config(args)
        return

    # Require at least one file for normal operation
    if not args.files:
        parser.error("the following arguments are required: files")

    # Resolve device
    device = resolve_device(args.device) if args.device is not None else None

    # Detect no-audio-device condition and auto-set output
    if not args.dry_run and args.output is None and not has_audio_output():
        # In container: write to /output/; locally: write to current dir
        output_dir = Path("/output") if Path("/output").is_dir() else Path(".")
        auto_path = output_dir / f"{args.files[0].stem}.wav"
        console.print(
            f"[yellow]No audio device detected. "
            f"Output will be saved to: {auto_path}[/yellow]"
        )
        args.output = auto_path

    # Parse page ranges
    pages = parse_page_ranges(args.pages) if args.pages is not None else None

    # Validate files exist
    for f in args.files:
        if not f.is_file():
            console.print(f"[red]Error: File not found: {f}[/red]")
            sys.exit(1)

    # Batch: auto-generate output names if --output given with multiple files
    multi = len(args.files) > 1

    try:
        for file_path in args.files:
            if multi:
                console.rule(f"[bold]{file_path.name}[/bold]")

            output = args.output
            if multi and output is not None:
                output = output.parent / f"{file_path.stem}.wav"

            asyncio.run(read_aloud(
                file_path,
                args.voice,
                args.uri,
                output,
                dry_run=args.dry_run,
                pages=pages,
                start=args.start,
                end=args.end,
                device=device,
            ))
    except KeyboardInterrupt:
        if _HAS_SD:
            sd.stop()
        console.print("\n[yellow]Stopped.[/yellow]")


if __name__ == "__main__":
    main()
