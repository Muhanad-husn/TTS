"""Read Aloud CLI Tool — package constants."""

import logging
import os
from pathlib import Path

from rich.console import Console

VOICES = ["alba", "azelma", "cosette", "eponine", "fantine", "javert", "jean", "marius"]
DEFAULT_URI = os.environ.get("READ_ALOUD_URI", "tcp://localhost:10201")
MAX_PARAGRAPH_CHARS = 500
CONFIG_PATH = Path.home() / ".read_aloud.toml"

console = Console()
_LOGGER = logging.getLogger(__name__)
