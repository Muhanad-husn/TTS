"""Producer-consumer pipeline for synthesis and playback."""

import asyncio
import logging
import sys
import time

import numpy as np
import sounddevice as sd
from rich.live import Live

from read_aloud import console
from read_aloud.audio import has_audio_output
from read_aloud.display import _build_status_display
from read_aloud.keyboard import KeyboardListener
from read_aloud.models import PlaybackState, SynthesisResult
from read_aloud.tts import synthesize_on_connection

from wyoming.client import AsyncClient

_LOGGER = logging.getLogger(__name__)


async def _synthesizer_task(
    uri: str,
    paragraphs: list[str],
    voice: str,
    queue: asyncio.Queue[SynthesisResult | None],
) -> None:
    """Producer: synthesize paragraphs with fresh connections and enqueue results."""
    total = len(paragraphs)
    try:
        for i, para in enumerate(paragraphs, 1):
            preview = para[:80] + ("..." if len(para) > 80 else "")
            try:
                async with AsyncClient.from_uri(uri) as client:
                    pcm, rate, width, ch = await synthesize_on_connection(
                        client, para, voice
                    )
                await queue.put(SynthesisResult(
                    index=i, total=total, preview=preview,
                    pcm=pcm, rate=rate, width=width, channels=ch,
                ))
            except ConnectionRefusedError:
                await queue.put(SynthesisResult(
                    index=i, total=total, preview=preview,
                    error=f"Cannot connect to TTS server at {uri}. Is the Wyoming TTS server running?",
                ))
            except Exception as e:
                _LOGGER.debug("Synthesis failed for paragraph %d: %s", i, e, exc_info=True)
                await queue.put(SynthesisResult(
                    index=i, total=total, preview=preview, error=str(e),
                ))
    finally:
        await queue.put(None)  # sentinel


async def _player_task(
    queue: asyncio.Queue[SynthesisResult | None],
    loop: asyncio.AbstractEventLoop,
    device: int | str | None = None,
    keyboard: KeyboardListener | None = None,
) -> tuple[list[bytes], tuple[int, int, int] | None]:
    """Consumer: dequeue synthesis results and play them back.

    Returns (all_pcm_chunks, audio_format) for optional WAV export.
    """
    all_pcm: list[bytes] = []
    audio_format: tuple[int, int, int] | None = None
    stream: sd.OutputStream | None = None
    interactive = keyboard is not None and sys.stdin.isatty()
    state = PlaybackState()
    audio_available = has_audio_output()

    # Chunk size for interactivity: ~100ms at 24kHz = 2400 samples
    CHUNK_SAMPLES = 2400

    try:
        with Live(console=console, refresh_per_second=4, transient=True) as live:
            while True:
                if keyboard and keyboard.quit_event.is_set():
                    console.print("[yellow]Quit requested.[/yellow]")
                    break

                result = await queue.get()
                if result is None:
                    break  # sentinel -- synthesizer is done

                state.total = result.total
                state.current_index = result.index
                state.current_preview = result.preview
                if state.start_time == 0:
                    state.start_time = time.monotonic()

                live.update(_build_status_display(state, interactive))

                if result.error:
                    console.print(f"  [red]ERROR: {result.error}[/red]")
                    state.completed_count += 1
                    continue

                if not result.pcm:
                    _LOGGER.debug("Empty audio returned for paragraph %d", result.index)
                    state.completed_count += 1
                    continue

                audio_format = (result.rate, result.width, result.channels)
                all_pcm.append(result.pcm)

                if result.width != 2:
                    console.print(
                        f"  [red]PLAYBACK ERROR: Unsupported sample width: {result.width}[/red]"
                    )
                    state.completed_count += 1
                    continue

                samples = np.frombuffer(result.pcm, dtype=np.int16)
                if result.channels > 1:
                    samples = samples.reshape(-1, result.channels)

                # Skip playback when no audio device is available
                if not audio_available:
                    state.completed_count += 1
                    live.update(_build_status_display(state, interactive))
                    # Still append inter-paragraph silence to WAV data
                    if result.index < result.total:
                        pause_samples = np.zeros(result.rate * 2, dtype=np.int16)
                        if result.channels > 1:
                            pause_samples = pause_samples.reshape(-1, result.channels)
                        all_pcm.append(pause_samples.tobytes())
                    continue

                # Lazily open the output stream on first valid audio
                if stream is None:
                    device_kwargs = {"device": device} if device is not None else {}
                    stream = sd.OutputStream(
                        samplerate=result.rate,
                        channels=result.channels,
                        dtype="int16",
                        **device_kwargs,
                    )
                    stream.start()

                # Write in ~100ms chunks for responsive pause/skip
                skip_this = False
                total_samples = len(samples)
                offset = 0

                while offset < total_samples:
                    # Check quit
                    if keyboard and keyboard.quit_event.is_set():
                        break
                    # Check skip
                    if keyboard and keyboard.skip_event.is_set():
                        keyboard.skip_event.clear()
                        skip_this = True
                        break
                    # Check pause
                    if keyboard and keyboard.pause_event.is_set():
                        state.paused = True
                        live.update(_build_status_display(state, interactive))
                        while keyboard.pause_event.is_set():
                            if keyboard.quit_event.is_set() or keyboard.skip_event.is_set():
                                break
                            await asyncio.sleep(0.05)
                        state.paused = False
                        live.update(_build_status_display(state, interactive))
                        if keyboard.skip_event.is_set():
                            keyboard.skip_event.clear()
                            skip_this = True
                            break

                    end = min(offset + CHUNK_SAMPLES, total_samples)
                    chunk = samples[offset:end]
                    try:
                        await loop.run_in_executor(None, stream.write, chunk)
                    except Exception as e:
                        _LOGGER.debug("Playback failed: %s", e, exc_info=True)
                        console.print(f"  [red]PLAYBACK ERROR: {e}[/red]")
                        skip_this = True
                        break
                    offset = end

                if keyboard and keyboard.quit_event.is_set():
                    break

                state.completed_count += 1
                live.update(_build_status_display(state, interactive))

                # Insert a 2-second silence between paragraphs
                if not skip_this and result.index < result.total:
                    pause_samples = np.zeros(result.rate * 2, dtype=np.int16)
                    if result.channels > 1:
                        pause_samples = pause_samples.reshape(-1, result.channels)
                    pause_bytes = pause_samples.tobytes()
                    all_pcm.append(pause_bytes)
                    try:
                        await loop.run_in_executor(None, stream.write, pause_samples)
                    except Exception as e:
                        _LOGGER.debug("Pause playback failed: %s", e, exc_info=True)
    finally:
        if stream is not None:
            stream.stop()
            stream.close()

    return all_pcm, audio_format
