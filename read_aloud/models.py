"""Dataclasses shared across modules."""

from dataclasses import dataclass


@dataclass
class SynthesisResult:
    """Result from synthesizing a single paragraph."""
    index: int
    total: int
    preview: str
    pcm: bytes = b""
    rate: int = 24000
    width: int = 2
    channels: int = 1
    error: str | None = None


@dataclass
class PlaybackState:
    """Tracks playback progress for the live display."""
    current_index: int = 0
    total: int = 0
    start_time: float = 0.0
    completed_count: int = 0
    paused: bool = False
    current_preview: str = ""
