"""Wyoming TTS client helpers."""

import asyncio
import time

from rich.table import Table
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.client import AsyncClient
from wyoming.error import Error
from wyoming.info import Describe, Info
from wyoming.tts import Synthesize, SynthesizeVoice

from read_aloud import console


async def synthesize_on_connection(
    client: AsyncClient, text: str, voice: str
) -> tuple[bytes, int, int, int]:
    """Synthesize text on an already-connected Wyoming client.

    Returns (pcm_bytes, sample_rate, sample_width, channels).
    """
    voice_obj = SynthesizeVoice(name=voice)
    await client.write_event(Synthesize(text=text, voice=voice_obj).event())

    sample_rate = 24000
    sample_width = 2
    channels = 1
    audio_chunks: list[bytes] = []

    while True:
        event = await client.read_event()
        if event is None:
            raise ConnectionError("Server closed connection unexpectedly")

        if AudioStart.is_type(event.type):
            audio_start = AudioStart.from_event(event)
            sample_rate = audio_start.rate
            sample_width = audio_start.width
            channels = audio_start.channels

        elif AudioChunk.is_type(event.type):
            chunk = AudioChunk.from_event(event)
            audio_chunks.append(chunk.audio)

        elif AudioStop.is_type(event.type):
            break

        elif Error.is_type(event.type):
            err = Error.from_event(event)
            raise RuntimeError(f"Server error: {err.text}")

    return b"".join(audio_chunks), sample_rate, sample_width, channels


async def wait_for_server(uri: str, timeout: float = 120, interval: float = 3) -> None:
    """Block until the Wyoming server responds to a Describe request."""
    deadline = time.monotonic() + timeout
    attempt = 0

    with console.status(
        f"[bold cyan]Waiting for TTS server at {uri}...[/bold cyan]"
    ) as status:
        while True:
            attempt += 1
            try:
                async with AsyncClient.from_uri(uri) as client:
                    await client.write_event(Describe().event())
                    event = await asyncio.wait_for(client.read_event(), timeout=10)
                    if event is not None and Info.is_type(event.type):
                        return
            except (ConnectionRefusedError, ConnectionError, OSError, asyncio.TimeoutError):
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"TTS server at {uri} not ready after {timeout}s. "
                    "Check that the container is running: docker compose logs"
                )
            status.update(
                f"[bold cyan]Waiting for TTS server at {uri}... "
                f"(attempt {attempt})[/bold cyan]"
            )
            await asyncio.sleep(interval)


async def list_server_voices(uri: str) -> None:
    """Connect to the server, send Describe, and display available voices."""
    try:
        async with AsyncClient.from_uri(uri) as client:
            await client.write_event(Describe().event())
            event = await asyncio.wait_for(client.read_event(), timeout=10)
            if event is None or not Info.is_type(event.type):
                console.print("[red]Error: Unexpected response from server[/red]")
                return
            info = Info.from_event(event)
    except (ConnectionRefusedError, ConnectionError, OSError) as e:
        console.print(f"[red]Error: Cannot connect to server at {uri}: {e}[/red]")
        return
    except asyncio.TimeoutError:
        console.print(f"[red]Error: Server at {uri} timed out[/red]")
        return

    table = Table(title="Available Voices")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="white")
    table.add_column("Languages", style="green")

    for tts_prog in info.tts:
        for voice in sorted(tts_prog.voices, key=lambda v: v.name):
            langs = ", ".join(voice.languages) if voice.languages else ""
            table.add_row(voice.name, voice.description or "", langs)

    console.print(table)
