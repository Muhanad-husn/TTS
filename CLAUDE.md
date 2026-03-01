# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Wyoming Protocol TTS server that bridges [Pocket-TTS](https://github.com/kyutai-labs/pocket-tts) (a fast, local neural TTS engine) to Home Assistant via the Wyoming protocol. Supports Zeroconf/mDNS auto-discovery.

## Architecture

**Single-file server**: All server logic lives in `wyoming_tts_server.py` (~500 lines). It implements `PocketTTSEventHandler(AsyncEventHandler)` which handles Wyoming protocol events (`Describe`, `Synthesize`, `SynthesizeStart/Chunk/Stop`).

**Key design decisions:**
- **Serialized synthesis**: A module-level `_VOICE_LOCK` (asyncio.Lock) ensures only one TTS call runs at a time. This is intentional.
- **Voice state caching**: All 8 voice states are pre-loaded at startup into `_VOICE_STATES` dict and reused with `copy_state=True`.
- **Sacrificial prefix hack**: `"... "` is prepended to all text to prevent the first word from being swallowed by Pocket-TTS's audio-prompt blend region. The prefix audio is then trimmed via silence gap detection. The env vars `PREFIX_MIN_DURATION`, `PREFIX_MAX_DURATION`, and `PREFIX_SILENCE_GAP` tune this trimming. Do not remove this pattern without understanding the blend region problem.
- **Audio output**: Sample rate from model, 16-bit mono, streamed in 1024-sample chunks.

**Companion tool**: `read_aloud.py` is a standalone CLI client (not part of the server) that connects to the Wyoming server to read PDF/DOCX/MD/TXT files aloud using `sounddevice` for audio playback.

## Build & Run

This is a Docker-only project. There is no local Python dev environment setup, no pyproject.toml, no requirements.txt, and no test suite in this repo.

```bash
# Build image locally
docker build -t pocket-tts-wyoming .

# Run with compose (production)
docker compose up -d

# Run with debug overlay (writes WAV files to project dir)
docker compose -f docker-compose.yml -f docker-compose.debug.yml up -d

# View logs
docker compose logs -f pocket-tts-wyoming
```

**Inside the container**, `uv` (from `ghcr.io/astral-sh/uv:debian` base) is the package manager. Dependencies (`wyoming>=1.8,<2`, `zeroconf`) are added via `uv add` at build time. Pocket-TTS is cloned from upstream into `/app` at build time (no pinned commit).

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `WYOMING_PORT` | `10201` | Server listen port |
| `WYOMING_HOST` | `0.0.0.0` | Bind address |
| `DEFAULT_VOICE` | `alba` | Default voice (alba, marius, javert, jean, fantine, cosette, eponine, azelma) |
| `MODEL_VARIANT` | `b6369a24` | Pocket-TTS model checkpoint |
| `ZEROCONF` | *(unset)* | mDNS service name; set to enable auto-discovery |
| `DEBUG_WAV` | *(unset)* | Set to `true` to write debug WAV files to `/output/` |
| `PREFIX_MIN_DURATION` | `0.15` | Min seconds before looking for prefix silence gap |
| `PREFIX_MAX_DURATION` | `1.0` | Max seconds to search for prefix end |
| `PREFIX_SILENCE_GAP` | `0.08` | Min silence duration to identify gap after prefix |
| `PAUSE_ENABLED` | `true` | Enable punctuation-based pause insertion between segments |
| `PAUSE_SENTENCE` | `2.0` | Silence (seconds) inserted between sentences |
| `PAUSE_PARAGRAPH` | `2.0` | Silence (seconds) inserted at paragraph breaks |
| `PAUSE_SECTION` | `2.0` | Silence (seconds) inserted at section breaks (`---`, `***`, etc.) |
| `PAUSE_CHAPTER` | `2.5` | Silence (seconds) inserted at chapter boundaries |

## CI/CD

`.github/workflows/docker-publish.yml` builds and pushes to `ghcr.io/ikidd`. It also runs on a daily schedule to check for upstream Pocket-TTS changes, and auto-commits SHA/timestamp updates to README.md with the `[workflow]` suffix. These automated commits land directly on master.
