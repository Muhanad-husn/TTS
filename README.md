# Pocket-TTS Wyoming + Read Aloud

> Fork of [ikidd/pocket-tts-wyoming](https://github.com/ikidd/pocket-tts-wyoming) — a Wyoming protocol server for [Pocket-TTS](https://github.com/kyutai-labs/pocket-tts) (fast, local neural TTS).
> This fork adds **Read Aloud**, a CLI tool that reads PDF, DOCX, EPUB, and Markdown files aloud through the TTS server.

## Quick Start

### 1. Start the TTS server

```bash
docker compose up -d
```

First run downloads ~500MB of model weights. Subsequent starts are fast thanks to volume-cached models.

### 2. Read a document aloud

Install the client dependencies:

```bash
pip install -r requirements.txt
```

Then read a document:

```bash
python read_aloud.py my_document.pdf
```

Or use the convenience scripts that start the server and launch the reader in one step:

```bash
# Linux / macOS
./start.sh my_document.pdf

# Windows (PowerShell)
.\start.ps1 my_document.pdf
```

See [READ_ALOUD.md](READ_ALOUD.md) for full documentation — voices, interactive controls, WAV export, device selection, config files, and more.

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
- **⏳ Last Build On**: 2026-03-01 00:43:22 UTC
- **🔄 Last Run**: 2026-03-01 00:43:22 UTC
- **Last Upstream SHA**: b942bc423b62bc102cd2d40f9e4bf1a75f629e76
