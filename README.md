<div align="center">

# Pocket-TTS Wyoming + Read Aloud

**Local, fast, neural text-to-speech — from documents to speech in one command.**

[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)](https://github.com/Muhanad-husn/TTS/pkgs/container/pocket-tts-wyoming)
[![Wyoming Protocol](https://img.shields.io/badge/Wyoming-Protocol-5D3FD3)](https://github.com/rhasspy/wyoming)
[![Pocket-TTS](https://img.shields.io/badge/Engine-Pocket--TTS-FF6F00)](https://github.com/kyutai-labs/pocket-tts)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-compatible-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![License](https://img.shields.io/github/license/Muhanad-husn/TTS)](LICENSE)

</div>

---

| | |
|---|---|
| **What** | A Wyoming protocol TTS server powered by [Pocket-TTS](https://github.com/kyutai-labs/pocket-tts) — a fast, local neural TTS engine by Kyutai Labs. Includes **Read Aloud**, a CLI tool that reads PDF, DOCX, EPUB, and Markdown files aloud. |
| **Why** | Fully offline, privacy-respecting speech synthesis. No cloud APIs, no subscriptions — just fast, natural-sounding TTS running on your own hardware. |
| **For whom** | Home Assistant users, self-hosters, accessibility enthusiasts, anyone who wants local TTS. |
| **Voices** | 8 built-in voices: `alba` `marius` `javert` `jean` `fantine` `cosette` `eponine` `azelma` |
| **Runs on** | Docker (CPU). ~500 MB model download on first run, cached thereafter. |
| **Based on** | Fork of [ikidd/pocket-tts-wyoming](https://github.com/ikidd/pocket-tts-wyoming) |

---

## Quick Start

### Prerequisites

You need two things installed on your computer:

- **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** — download and install for your operating system (Windows, macOS, or Linux). Launch it after installing.
- **[Git](https://git-scm.com/downloads)** *(optional)* — used to download the project. If you'd rather not install Git, you can download the project as a ZIP file instead (see below).

### 1. Get the project

**Option A — Clone with Git** (recommended):

Open a terminal (Command Prompt or PowerShell on Windows, Terminal on macOS/Linux) and run:

```bash
git clone https://github.com/Muhanad-husn/TTS.git
```

**Option B — Download as ZIP** (no Git needed):

1. Go to [github.com/Muhanad-husn/TTS](https://github.com/Muhanad-husn/TTS)
2. Click the green **Code** button, then **Download ZIP**
3. Extract the ZIP file to a folder on your computer

### 2. Open the project folder in a terminal

Navigate into the project directory you just downloaded:

```bash
cd TTS
```

> **Tip**: On Windows, you can also open the folder in File Explorer, click the address bar, type `cmd`, and press Enter to open a terminal already inside the folder.

### 3. Start the TTS server

Make sure Docker Desktop is running, then start the server:

```bash
docker compose up -d
```

First run downloads ~500 MB of model weights. Subsequent starts are fast thanks to volume-cached models.

### 4. Read a document aloud

No local Python needed — the Read Aloud tool runs entirely in Docker:

```bash
# Linux / macOS
./start.sh my_document.pdf

# Windows (PowerShell)
.\start.ps1 my_document.pdf

# With options
./start.sh --voice cosette --pages 1-5 my_document.pdf
```

The script starts the TTS server (if not already running), copies the file into a container, synthesizes speech, and writes the WAV output to the `output/` directory.

> **Note**: Docker containers cannot access host audio devices on Windows/macOS, so containerized usage produces WAV files. For live speaker playback, use the [local Python setup](#local-python-alternative).

You can also use `docker compose` directly:

```bash
docker compose up -d pocket-tts-wyoming
docker compose run --rm read-aloud --voice cosette /input/my_doc.pdf
```

See [READ_ALOUD.md](READ_ALOUD.md) for full documentation — voices, interactive controls, WAV export, device selection, config files, and more.

### Local Python alternative

If you prefer live audio playback through your speakers, install the client locally:

```bash
pip install -r requirements.txt
python read_aloud.py my_document.pdf
```

## Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `WYOMING_PORT` | `10201` | The port the Wyoming protocol server listens on |
| `WYOMING_HOST` | `0.0.0.0` | Network interface to bind to |
| `DEFAULT_VOICE` | `alba` | Default voice when none is specified |
| `MODEL_VARIANT` | `b6369a24` | Pocket-TTS model checkpoint |
| `ZEROCONF` | `pocket-tts` | mDNS service name for auto-discovery; set to empty string to disable |

## Available Voices

alba, marius, javert, jean, fantine, cosette, eponine, azelma

## Home Assistant Integration

The server supports Zeroconf/mDNS for automatic discovery.

1. Start the Docker container
2. Go to Settings -> Devices & Services -> Add Integration
3. Search for "Wyoming Protocol"
4. The server should appear in the "Discovered" section, or enter `tcp://<server-ip>:10201` manually
5. Configure a Voice Assistant pipeline to use the TTS service and select a voice

## Debug Mode & Timing Tunables

Debug mode writes WAV files for each synthesis request and exposes timing tunables for diagnosing audio issues (such as the first word being cut off).

```bash
docker compose -f docker-compose.yml -f docker-compose.debug.yml up -d --build
```

This enables:
- **WAV file output**: Each synthesis writes a debug WAV file to the project directory
- **Timing tunables**: Environment variables to adjust the sacrificial prefix trimming

### Background

Audio-prompt based TTS models like Pocket-TTS can "swallow" the first word into a blend region when transitioning from the voice prompt. To prevent this, a sacrificial prefix (`"..."`) is prepended to all text and then trimmed from the resulting audio. Debug mode lets you tune this trimming.

### Timing Tunables

| Variable | Default | Description |
|----------|---------|-------------|
| `PREFIX_MIN_DURATION` | `0.15` | Minimum seconds before looking for the pause after the prefix |
| `PREFIX_MAX_DURATION` | `1.0` | Maximum seconds to search for the prefix end |
| `PREFIX_SILENCE_GAP` | `0.08` | Minimum silence duration (seconds) to identify the gap after the prefix |

**Tuning tips:**
- If you hear part of the "..." prefix, decrease `PREFIX_SILENCE_GAP` to catch shorter pauses
- If the first syllable is still being cut, increase `PREFIX_MIN_DURATION`
- Different voices speak at different speeds, so optimal values may vary

## Troubleshooting

- **Slow startup**: First run downloads ~500MB of model weights. Use volume mounts to persist the cache.
- **Connection issues**: Verify port 10201 is open and check logs with `docker compose logs pocket-tts-wyoming`
- **Voice not found**: Ensure the voice name matches one of the 8 predefined voices listed above.
- **First word cut off**: Run in debug mode and check the WAV files. Adjust the timing tunables as needed.

## Acknowledgments

- [ikidd/pocket-tts-wyoming](https://github.com/ikidd/pocket-tts-wyoming) — upstream Wyoming server for Pocket-TTS
- [kyutai-labs/pocket-tts](https://github.com/kyutai-labs/pocket-tts) — the TTS engine (MIT license)
- [rhasspy/wyoming](https://github.com/rhasspy/wyoming) — the Wyoming voice assistant protocol

## 📅 Release Status
- **⏳ Last Build On**: 2026-03-13 00:16:37 UTC
- **🔄 Last Run**: 2026-03-15 00:20:00 UTC
- **Last Upstream SHA**: 25e1b673cd4f6f1ac11cdc370ea1e7010d2376df
