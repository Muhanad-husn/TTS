#!/usr/bin/env python3
"""
Wyoming Protocol TTS Server for Pocket-TTS

Implements Wyoming protocol TTS server that wraps pocket-tts,
exposing available voices to Home Assistant for selection.
"""

import argparse
import asyncio
import logging
import os
import re
import wave
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Optional

import numpy

from pocket_tts import TTSModel
from pocket_tts.default_parameters import DEFAULT_VARIANT
from pocket_tts.utils.utils import PREDEFINED_VOICES
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.error import Error
from wyoming.event import Event
from wyoming.info import Attribution, Describe, Info, TtsProgram, TtsVoice
from wyoming.server import AsyncEventHandler, AsyncServer, AsyncTcpServer
from wyoming.tts import (
    Synthesize,
    SynthesizeChunk,
    SynthesizeStart,
    SynthesizeStop,
    SynthesizeStopped,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = int(os.environ.get("WYOMING_PORT", "10201"))
DEFAULT_VOICE = os.environ.get("DEFAULT_VOICE", "alba")
MODEL_VARIANT = os.environ.get("MODEL_VARIANT", DEFAULT_VARIANT)
DEBUG_WAV = os.environ.get("DEBUG_WAV", "").lower() in ("true", "1", "yes")

# Prefix trimming tunables (in seconds)
# Minimum time before looking for the pause after the sacrificial prefix
PREFIX_MIN_DURATION = float(os.environ.get("PREFIX_MIN_DURATION", "0.15"))
# Maximum time to search for the prefix end
PREFIX_MAX_DURATION = float(os.environ.get("PREFIX_MAX_DURATION", "1.0"))
# Minimum silence duration to consider it the gap after the prefix
PREFIX_SILENCE_GAP = float(os.environ.get("PREFIX_SILENCE_GAP", "0.08"))

# Pause insertion tunables (in seconds). Set PAUSE_ENABLED=false to disable.
PAUSE_ENABLED = os.environ.get("PAUSE_ENABLED", "true").lower() in ("true", "1", "yes")
PAUSE_SENTENCE = float(os.environ.get("PAUSE_SENTENCE", "2.0"))
PAUSE_PARAGRAPH = float(os.environ.get("PAUSE_PARAGRAPH", "2.0"))
PAUSE_SECTION = float(os.environ.get("PAUSE_SECTION", "2.0"))
PAUSE_CHAPTER = float(os.environ.get("PAUSE_CHAPTER", "2.5"))

_VOICE_STATES: dict[str, dict] = {}
_VOICE_LOCK = asyncio.Lock()


@dataclass
class TextSegment:
    """A segment of text with an associated pause duration after it."""
    text: str
    pause_after: float


def _is_synthesizable(text: str) -> bool:
    """Return True if text contains actual words to synthesize (not just whitespace/punctuation)."""
    return bool(re.search(r'[a-zA-Z0-9]', text))


def segment_text_for_pauses(raw_text: str) -> list[TextSegment]:
    """Split text into segments with pause durations based on structural boundaries.

    Detects chapter titles, section breaks, paragraph breaks, and sentence boundaries.
    Each segment gets a pause_after value based on the strongest boundary that follows it.
    """
    # Split into lines for structural analysis
    lines = raw_text.split('\n')

    # Classify each line
    CHAPTER_RE = re.compile(
        r'^(?:chapter\s+\S+|part\s+\S+|book\s+\S+|prologue|epilogue|introduction|preface|afterword)\s*[:\-—]?\s*.*$',
        re.IGNORECASE,
    )
    SECTION_BREAK_RE = re.compile(r'^[\s]*[-*=~#]{3,}[\s]*$')
    ALL_CAPS_TITLE_RE = re.compile(r'^[A-Z][A-Z\s\d:,\-—]{2,}$')

    # Group lines into blocks separated by structural markers
    segments: list[TextSegment] = []

    # First pass: group lines into paragraphs and identify structural elements
    blocks: list[tuple[str, str]] = []  # (type, text) where type is 'chapter', 'section', 'paragraph'
    current_paragraph_lines: list[str] = []

    def flush_paragraph():
        if current_paragraph_lines:
            text = ' '.join(current_paragraph_lines)
            text = ' '.join(text.strip().split())  # normalize whitespace
            if text:
                blocks.append(('paragraph', text))
            current_paragraph_lines.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Section break (---, ***, ===, etc.)
        if SECTION_BREAK_RE.match(stripped):
            flush_paragraph()
            blocks.append(('section', ''))
            i += 1
            continue

        # Chapter title detection
        if stripped and CHAPTER_RE.match(stripped):
            flush_paragraph()
            blocks.append(('chapter', stripped))
            i += 1
            continue

        # All-caps short title followed by a blank line (look ahead)
        if stripped and ALL_CAPS_TITLE_RE.match(stripped) and len(stripped) <= 60:
            next_blank = (i + 1 < len(lines) and not lines[i + 1].strip()) if i + 1 < len(lines) else True
            if next_blank:
                flush_paragraph()
                blocks.append(('chapter', stripped))
                i += 1
                continue

        # Blank line = paragraph boundary
        if not stripped:
            flush_paragraph()
            i += 1
            continue

        # Regular text line
        current_paragraph_lines.append(stripped)
        i += 1

    flush_paragraph()

    # Second pass: split paragraphs into sentences and assign pause durations
    for block_idx, (block_type, block_text) in enumerate(blocks):
        if block_type == 'section':
            # Section break itself has no text, but it affects the pause of the preceding segment
            if segments:
                segments[-1].pause_after = max(segments[-1].pause_after, PAUSE_SECTION)
            continue

        if block_type == 'chapter':
            # Chapter title: apply chapter pause to preceding segment (if any)
            if segments:
                segments[-1].pause_after = max(segments[-1].pause_after, PAUSE_CHAPTER)
            # Add the title text as its own segment
            if _is_synthesizable(block_text):
                segments.append(TextSegment(text=block_text, pause_after=PAUSE_CHAPTER))
            continue

        # Regular paragraph: split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', block_text)
        for sent_idx, sentence in enumerate(sentences):
            sentence = ' '.join(sentence.strip().split())
            if not sentence:
                continue

            # Determine pause: last sentence in paragraph gets paragraph pause,
            # others get sentence pause
            is_last_sentence = sent_idx == len(sentences) - 1
            if is_last_sentence:
                # Check what follows this paragraph
                pause = PAUSE_PARAGRAPH
            else:
                pause = PAUSE_SENTENCE

            segments.append(TextSegment(text=sentence, pause_after=pause))

    # Remove trailing pause from the very last segment (trimmed later anyway)
    if segments:
        segments[-1].pause_after = 0.0

    return segments


class PocketTTSEventHandler(AsyncEventHandler):
    """Event handler for Pocket-TTS Wyoming server."""

    def __init__(
        self,
        wyoming_info: Info,
        cli_args: argparse.Namespace,
        tts_model: TTSModel,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.cli_args = cli_args
        self.wyoming_info_event = wyoming_info.event()
        self.tts_model = tts_model
        self.is_streaming: Optional[bool] = None
        self._synthesize: Optional[Synthesize] = None
        self._stream_text: str = ""

    async def handle_event(self, event: Event) -> bool:
        """Handle incoming Wyoming protocol events."""
        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info_event)
            _LOGGER.debug("Sent info")
            return True

        try:
            if Synthesize.is_type(event.type):
                if self.is_streaming:
                    # Ignore since this is only sent for compatibility reasons.
                    # For streaming, we expect:
                    # [synthesize-start] -> [synthesize-chunk]+ -> [synthesize]? -> [synthesize-stop]
                    return True

                synthesize = Synthesize.from_event(event)
                await self._handle_synthesize(synthesize, send_start=True, send_stop=True)
                return True

            if SynthesizeStart.is_type(event.type):
                stream_start = SynthesizeStart.from_event(event)
                self.is_streaming = True
                self._stream_text = ""
                self._synthesize = Synthesize(text="", voice=stream_start.voice)
                _LOGGER.debug("Text stream started: voice=%s", stream_start.voice)
                return True

            if SynthesizeChunk.is_type(event.type):
                assert self._synthesize is not None
                stream_chunk = SynthesizeChunk.from_event(event)
                self._stream_text += stream_chunk.text
                _LOGGER.debug("Received stream chunk: %s", stream_chunk.text[:50])
                return True

            if SynthesizeStop.is_type(event.type):
                assert self._synthesize is not None
                if self._stream_text.strip():
                    self._synthesize.text = self._stream_text.strip()
                    await self._handle_synthesize(
                        self._synthesize, send_start=True, send_stop=True
                    )

                await self.write_event(SynthesizeStopped().event())
                self.is_streaming = False
                self._stream_text = ""
                _LOGGER.debug("Text stream stopped")
                return True

            return True
        except Exception as err:
            await self.write_event(
                Error(text=str(err), code=err.__class__.__name__).event()
            )
            raise err

    def _synthesize_segment(self, text: str, voice_state, sample_rate: int) -> Optional[numpy.ndarray]:
        """Synthesize a single text segment with prefix hack. Returns float32 audio or None."""
        # Add sacrificial prefix to prevent the first word from being swallowed
        prefixed_text = "... " + text

        audio_chunks = self.tts_model.generate_audio_stream(
            model_state=voice_state, text_to_generate=prefixed_text, copy_state=True
        )

        all_audio_arrays = []
        for audio_chunk in audio_chunks:
            audio_array = audio_chunk.detach().cpu().numpy()
            all_audio_arrays.append(audio_array)

        if not all_audio_arrays:
            return None

        full_audio = numpy.concatenate(all_audio_arrays)

        # Find and remove the sacrificial prefix ("...") by detecting the pause after it
        silence_threshold = 0.01
        max_amplitude = numpy.abs(full_audio).max()
        if max_amplitude == 0:
            return None
        threshold = max_amplitude * silence_threshold

        min_prefix_samples = int(sample_rate * PREFIX_MIN_DURATION)
        max_prefix_samples = int(sample_rate * PREFIX_MAX_DURATION)
        min_silence_samples = int(sample_rate * PREFIX_SILENCE_GAP)

        prefix_end = 0
        if len(full_audio) > min_prefix_samples:
            search_end = min(len(full_audio), max_prefix_samples)
            is_silent = numpy.abs(full_audio[:search_end]) < threshold

            i = min_prefix_samples
            while i < search_end:
                if is_silent[i]:
                    silence_start = i
                    while i < search_end and is_silent[i]:
                        i += 1
                    silence_length = i - silence_start
                    if silence_length >= min_silence_samples:
                        prefix_end = i
                        break
                else:
                    i += 1

        if prefix_end > 0:
            _LOGGER.debug("Trimming prefix: %d samples (%.3fs)",
                          prefix_end, prefix_end / sample_rate)
            full_audio = full_audio[prefix_end:]

        # Trim leading silence
        non_silent_indices = numpy.where(numpy.abs(full_audio) > threshold)[0]
        if len(non_silent_indices) > 0:
            padding_samples = int(sample_rate * 0.05)  # 50ms padding
            first_non_silent = max(0, non_silent_indices[0] - padding_samples)
            full_audio = full_audio[first_non_silent:]

            # Trim trailing silence
            non_silent_indices = numpy.where(numpy.abs(full_audio) > threshold)[0]
            if len(non_silent_indices) > 0:
                last_non_silent = non_silent_indices[-1] + padding_samples
                full_audio = full_audio[:last_non_silent + 1]

        if len(full_audio) == 0:
            return None

        return full_audio

    async def _handle_synthesize(
        self, synthesize: Synthesize, send_start: bool = True, send_stop: bool = True
    ) -> bool:
        """Handle synthesis request."""
        _LOGGER.debug(synthesize)

        raw_text = synthesize.text

        if not raw_text.strip():
            _LOGGER.warning("Empty text received")
            if send_stop:
                await self.write_event(AudioStop().event())
            return True

        voice_name: Optional[str] = None

        if synthesize.voice is not None:
            voice_name = synthesize.voice.name

        if voice_name is None:
            voice_name = self.cli_args.voice

        # Extract voice name from model name if it's in format "pocket-tts-{voice}"
        if voice_name and voice_name.startswith("pocket-tts-"):
            voice_name = voice_name.replace("pocket-tts-", "", 1)

        if voice_name not in PREDEFINED_VOICES:
            _LOGGER.warning(
                "Voice '%s' not found, using default '%s'", voice_name, self.cli_args.voice
            )
            voice_name = self.cli_args.voice

        assert voice_name is not None

        async with _VOICE_LOCK:
            global _VOICE_STATES
            if voice_name not in _VOICE_STATES:
                _LOGGER.info("Loading voice state for: %s", voice_name)
                try:
                    _VOICE_STATES[voice_name] = self.tts_model.get_state_for_audio_prompt(
                        voice_name
                    )
                except Exception as e:
                    _LOGGER.error("Failed to load voice state for %s: %s", voice_name, e)
                    await self.write_event(
                        Error(
                            text=f"Failed to load voice: {voice_name}",
                            code="VoiceLoadError",
                        ).event()
                    )
                    return True

            voice_state = _VOICE_STATES[voice_name]

            try:
                sample_rate = self.tts_model.sample_rate
                width = 2
                channels = 1
                bytes_per_sample = width * channels
                samples_per_chunk = 1024
                bytes_per_chunk = bytes_per_sample * samples_per_chunk

                # Build segments
                if PAUSE_ENABLED:
                    segments = segment_text_for_pauses(raw_text)
                else:
                    # Disabled: single segment with original whitespace normalization
                    text = " ".join(raw_text.strip().splitlines())
                    segments = [TextSegment(text=text, pause_after=0.0)]

                _LOGGER.info(
                    "Synthesizing %d segment(s) (voice: %s, total chars: %d)",
                    len(segments), voice_name, sum(len(s.text) for s in segments),
                )

                if send_start:
                    await self.write_event(
                        AudioStart(
                            rate=sample_rate,
                            width=width,
                            channels=channels,
                        ).event(),
                    )

                all_audio: list[numpy.ndarray] = []

                for seg_idx, segment in enumerate(segments):
                    if _is_synthesizable(segment.text):
                        _LOGGER.debug(
                            "Segment %d/%d: '%s' (pause_after=%.2fs)",
                            seg_idx + 1, len(segments),
                            segment.text[:80], segment.pause_after,
                        )
                        audio = self._synthesize_segment(
                            segment.text, voice_state, sample_rate
                        )
                        if audio is not None:
                            all_audio.append(audio)

                    if segment.pause_after > 0:
                        silence = numpy.zeros(
                            int(sample_rate * segment.pause_after), dtype=numpy.float32
                        )
                        all_audio.append(silence)

                if not all_audio:
                    if send_stop:
                        await self.write_event(AudioStop().event())
                    return True

                full_audio = numpy.concatenate(all_audio)

                # Trim trailing silence from the very end (no dangling pause)
                silence_threshold = 0.01
                max_amplitude = numpy.abs(full_audio).max()
                if max_amplitude > 0:
                    threshold = max_amplitude * silence_threshold
                    non_silent_indices = numpy.where(numpy.abs(full_audio) > threshold)[0]
                    if len(non_silent_indices) > 0:
                        padding_samples = int(sample_rate * 0.05)
                        last_non_silent = non_silent_indices[-1] + padding_samples
                        full_audio = full_audio[:last_non_silent + 1]

                full_audio = (full_audio.clip(-1.0, 1.0) * 32767).astype("int16")
                audio_bytes = full_audio.tobytes()

                # Write debug WAV file if enabled
                if self.cli_args.debug_wav:
                    try:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                        wav_filename = f"/output/debug_{voice_name}_{timestamp}.wav"
                        with wave.open(wav_filename, "wb") as wav_file:
                            wav_file.setnchannels(channels)
                            wav_file.setsampwidth(width)
                            wav_file.setframerate(sample_rate)
                            wav_file.writeframes(audio_bytes)
                        _LOGGER.info("Debug WAV file written: %s", wav_filename)
                    except Exception as e:
                        _LOGGER.warning("Failed to write debug WAV file: %s", e)

                num_chunks = int(numpy.ceil(len(audio_bytes) / bytes_per_chunk))
                for i in range(num_chunks):
                    offset = i * bytes_per_chunk
                    chunk = audio_bytes[offset : offset + bytes_per_chunk]
                    await self.write_event(
                        AudioChunk(
                            audio=chunk,
                            rate=sample_rate,
                            width=width,
                            channels=channels,
                        ).event(),
                    )

                if send_stop:
                    await self.write_event(AudioStop().event())

                _LOGGER.info("Synthesis complete")
            except Exception as e:
                _LOGGER.error("Error during synthesis: %s", e, exc_info=True)
                await self.write_event(
                    Error(text=str(e), code=e.__class__.__name__).event()
                )
                return True

        return True


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Wyoming Protocol TTS Server for Pocket-TTS"
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("WYOMING_HOST", "0.0.0.0"),
        help="Host to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port to listen on (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--voice",
        default=DEFAULT_VOICE,
        help=f"Default voice to use (default: {DEFAULT_VOICE})",
    )
    parser.add_argument(
        "--variant",
        default=MODEL_VARIANT,
        help=f"Model variant (default: {MODEL_VARIANT})",
    )
    parser.add_argument(
        "--uri",
        default=None,
        help="Server URI (e.g., tcp://0.0.0.0:10201). If not provided, constructed from --host and --port",
    )
    parser.add_argument(
        "--zeroconf",
        nargs="?",
        const="pocket-tts",
        help="Enable discovery over zeroconf with optional name (default: pocket-tts)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce logging output",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Log DEBUG messages",
    )
    parser.add_argument(
        "--debug-wav",
        action="store_true",
        help="Write complete WAV file to /output/ on every response (default: from DEBUG_WAV env var)",
    )
    parser.add_argument(
        "--log-format",
        default=logging.BASIC_FORMAT,
        help="Format for log messages",
    )

    args = parser.parse_args()
    
    # Override debug_wav from environment if not explicitly set via command line
    # Check environment variable at runtime (not just at module load)
    debug_wav_env = os.environ.get("DEBUG_WAV", "").lower() in ("true", "1", "yes")
    if not args.debug_wav:
        args.debug_wav = debug_wav_env

    log_level = logging.DEBUG if args.debug else (logging.ERROR if args.quiet else logging.INFO)
    logging.basicConfig(level=log_level, format=args.log_format)
    if args.debug_wav:
        _LOGGER.info("Debug WAV mode enabled - WAV files will be written to /output/ on every response")
    _LOGGER.debug(args)

    os.environ["MODEL_VARIANT"] = args.variant
    variant = os.environ.get("MODEL_VARIANT", MODEL_VARIANT)
    _LOGGER.info("Loading Pocket-TTS model (variant: %s)...", variant)
    tts_model = TTSModel.load_model(config=variant)
    _LOGGER.info("Model loaded successfully")
    _LOGGER.info("Sample rate: %d Hz", tts_model.sample_rate)

    _LOGGER.info("Pre-loading voice states for %d voices...", len(PREDEFINED_VOICES))
    for voice_name in PREDEFINED_VOICES:
        try:
            voice_state = tts_model.get_state_for_audio_prompt(voice_name)
            global _VOICE_STATES
            _VOICE_STATES[voice_name] = voice_state
            _LOGGER.info("Loaded voice state for: %s", voice_name)
        except Exception as e:
            _LOGGER.warning("Failed to load voice state for %s: %s", voice_name, e)
    _LOGGER.info("Voice states pre-loaded")

    voices = [
        TtsVoice(
            name=voice_name,
            description=f"Pocket-TTS voice: {voice_name}",
            attribution=Attribution(
                name="Kyutai Pocket-TTS",
                url="https://github.com/kyutai-labs/pocket-tts",
            ),
            installed=True,
            version=None,
            languages=["en"],
            speakers=None,
        )
        for voice_name in PREDEFINED_VOICES
    ]

    wyoming_info = Info(
        tts=[
            TtsProgram(
                name="pocket-tts",
                description="A fast, local, neural text to speech engine",
                attribution=Attribution(
                    name="Kyutai Pocket-TTS",
                    url="https://github.com/kyutai-labs/pocket-tts",
                ),
                installed=True,
                voices=sorted(voices, key=lambda v: v.name),
                version="1.0.1",
                supports_synthesize_streaming=True,
            )
        ],
    )

    if args.uri is None:
        args.uri = f"tcp://{args.host}:{args.port}"

    server = AsyncServer.from_uri(args.uri)

    zeroconf_name = args.zeroconf
    if not zeroconf_name:
        zeroconf_env = os.environ.get("ZEROCONF")
        if zeroconf_env:
            zeroconf_name = zeroconf_env if zeroconf_env != "true" else "pocket-tts"

    if zeroconf_name:
        if not isinstance(server, AsyncTcpServer):
            raise ValueError("Zeroconf requires tcp:// uri")

        from wyoming.zeroconf import HomeAssistantZeroconf
        import socket

        tcp_server: AsyncTcpServer = server
        zeroconf_host = tcp_server.host
        if zeroconf_host == "0.0.0.0" or not zeroconf_host:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                zeroconf_host = s.getsockname()[0]
                s.close()
            except Exception:
                zeroconf_host = "127.0.0.1"
        
        hass_zeroconf = HomeAssistantZeroconf(
            name=zeroconf_name, port=tcp_server.port, host=zeroconf_host
        )
        await hass_zeroconf.register_server()
        _LOGGER.debug("Zeroconf discovery enabled: name=%s, port=%d, host=%s", 
                     zeroconf_name, tcp_server.port, zeroconf_host)

    _LOGGER.info("Ready")
    _LOGGER.info("Available voices: %s", ", ".join(PREDEFINED_VOICES.keys()))
    await server.run(
        partial(
            PocketTTSEventHandler,
            wyoming_info,
            args,
            tts_model,
        )
    )


def run():
    """Run the server."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _LOGGER.info("Server stopped")


if __name__ == "__main__":
    run()
