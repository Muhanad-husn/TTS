# Read Aloud CLI Tool

A command-line tool that reads PDF, DOCX, EPUB, and Markdown files aloud using a [Pocket-TTS Wyoming](https://github.com/ikidd/pocket-tts-wyoming) server. Audio is streamed through your speakers in real-time, paragraph by paragraph, and can optionally be saved as a WAV file.

Features include interactive playback controls, rich terminal output with progress tracking, device selection, batch mode, and a config file for persisting defaults.

---

## Table of Contents

- [Docker Usage (recommended)](#docker-usage-recommended)
- [Prerequisites (local)](#prerequisites-local)
- [Installation (local)](#installation-local)
- [Quick Start](#quick-start)
- [Usage Reference](#usage-reference)
  - [Arguments](#arguments)
  - [Voices](#voices)
- [Examples](#examples)
  - [Read a PDF](#read-a-pdf)
  - [Read Markdown with a specific voice](#read-markdown-with-a-specific-voice)
  - [Save output to WAV](#save-output-to-wav)
  - [Connect to a remote server](#connect-to-a-remote-server)
  - [Dry run](#dry-run)
  - [Page ranges (PDF)](#page-ranges-pdf)
  - [Paragraph range](#paragraph-range)
  - [Read an EPUB](#read-an-epub)
  - [Device selection](#device-selection)
  - [List voices from server](#list-voices-from-server)
  - [Batch mode](#batch-mode)
  - [Debug mode](#debug-mode)
- [Interactive Controls](#interactive-controls)
- [Config File](#config-file)
- [How It Works](#how-it-works)
  - [Document Parsing](#document-parsing)
  - [Synthesis and Playback](#synthesis-and-playback)
  - [WAV Export](#wav-export)
- [Supported File Types](#supported-file-types)
- [Troubleshooting](#troubleshooting)

---

## Docker Usage (recommended)

The easiest way to use Read Aloud — no Python or dependencies required. Just Docker.

```bash
# Linux / macOS
./start.sh my_document.pdf

# Windows (PowerShell)
.\start.ps1 my_document.pdf

# With options
./start.sh --voice cosette --pages 1-5 my_document.pdf
```

The script:
1. Creates `input/` and `output/` directories
2. Copies your file into `input/`
3. Starts the TTS server (if not already running)
4. Runs Read Aloud in a container
5. Writes the resulting WAV to `output/`

You can also use `docker compose` directly:

```bash
# Start the TTS server
docker compose up -d pocket-tts-wyoming

# Run Read Aloud (file must be in input/)
docker compose run --rm read-aloud /input/my_document.pdf

# List available voices
docker compose run --rm read-aloud --list-voices

# Dry run (parse only, no synthesis)
docker compose run --rm read-aloud --dry-run /input/my_document.pdf
```

> **Note**: Docker Desktop on Windows/macOS cannot pass audio devices to containers. The containerized tool automatically detects this and saves output as WAV files instead of playing through speakers. For live speaker playback, use the [local Python setup](#prerequisites-local) below.

---

## Prerequisites (local)

For live audio playback through your speakers, you can run Read Aloud locally:

1. **Python 3.10+**
2. **A running Pocket-TTS Wyoming server** — the tool connects to it over TCP to synthesize speech. The server can be running locally, in Docker, or on a remote machine. See the main [README](README.md) for server setup instructions.
3. **Audio output device** — speakers or headphones connected to the machine running the tool.

## Installation (local)

Install the required Python packages:

```bash
pip install sounddevice PyMuPDF python-docx numpy "wyoming>=1.8,<2" rich ebooklib beautifulsoup4
```

| Package | Purpose |
|---|---|
| `sounddevice` | Real-time audio playback (bundles PortAudio on Windows) |
| `PyMuPDF` | PDF text extraction (imports as `fitz`) |
| `python-docx` | DOCX text extraction |
| `numpy` | Audio sample conversion |
| `wyoming` | Wyoming protocol client for communicating with the TTS server |
| `rich` | Colored output, progress display, tables, live status |
| `ebooklib` | EPUB parsing |
| `beautifulsoup4` | HTML text extraction from EPUB content |

Optional: `tomli` for config file support on Python 3.10 (Python 3.11+ has `tomllib` in the standard library).

No additional compilation or system-level dependencies are needed on Windows. On Linux, you may need PortAudio installed (`sudo apt install libportaudio2`).

## Quick Start

```bash
# Make sure your TTS server is running on localhost:10201, then:
python read_aloud.py my_document.pdf
```

That's it. The tool will parse the document, synthesize each paragraph, and play it through your speakers with a live progress display. Use `Space` to pause, `n` to skip, or `q` to quit during playback.

## Usage Reference

```
python read_aloud.py [-h] [--voice {alba,...}] [--uri URI] [--output FILE]
                     [--debug] [--dry-run] [--list-devices] [--device DEV]
                     [--list-voices] [--pages RANGE] [--start N] [--end N]
                     [--save-config] [FILE ...]
```

### Arguments

| Argument | Short | Required | Default | Description |
|---|---|---|---|---|
| `files` | | Yes* | | Path(s) to document(s) to read aloud |
| `--voice` | `-v` | No | `alba` | Voice to use for synthesis |
| `--uri` | `-u` | No | `tcp://localhost:10201` | Wyoming TTS server URI |
| `--output` | `-o` | No | *(interactive prompt)* | Path to save WAV file (skips the interactive save prompt) |
| `--debug` | | No | off | Enable debug logging to stderr |
| `--dry-run` | | No | off | Parse and display paragraphs without playing audio |
| `--list-devices` | | No | off | List audio output devices and exit |
| `--device` | `-d` | No | system default | Audio output device (index or name substring) |
| `--list-voices` | | No | off | Query server for available voices and exit |
| `--pages` | | No | all | Page range for PDFs (e.g., `1-5,8,10-12`) |
| `--start` | | No | 1 | Start at paragraph N (1-indexed) |
| `--end` | | No | last | End at paragraph N (1-indexed) |
| `--save-config` | | No | off | Save current flags as defaults to `~/.read_aloud.toml` |

\* Not required when using `--list-devices`, `--list-voices`, or `--save-config`.

### Voices

Eight voices are available, matching the Pocket-TTS voice set:

| Voice | Description |
|---|---|
| `alba` | Default voice |
| `azelma` | |
| `cosette` | |
| `eponine` | |
| `fantine` | |
| `javert` | |
| `jean` | |
| `marius` | |

All voices speak English. Voice quality and characteristics vary — try a few to find one you like. Use `--list-voices` to query the server for the full list.

## Examples

### Read a PDF

```bash
python read_aloud.py report.pdf
```

Parses the PDF, reads it aloud paragraph by paragraph with a live progress display, and prompts to save at the end.

### Read Markdown with a specific voice

```bash
python read_aloud.py notes.md --voice cosette
```

### Save output to WAV

```bash
# Auto-save to a specific file (no interactive prompt):
python read_aloud.py chapter1.pdf -o chapter1.wav

# Or let the tool prompt you after playback finishes:
python read_aloud.py chapter1.pdf
# ... plays audio ...
# Save audio as WAV? [y/N] y
# Filename [chapter1.wav]: <Enter>
# Saved: chapter1.wav (42.3s)
```

### Connect to a remote server

If your TTS server is running on another machine or a non-default port:

```bash
python read_aloud.py document.docx --uri tcp://192.168.1.50:10201
```

### Dry run

Preview parsed paragraphs without connecting to the server or playing audio:

```bash
python read_aloud.py document.pdf --dry-run
```

This displays a numbered list of all paragraphs with character counts — useful for verifying parsing before a long reading session.

### Page ranges (PDF)

Read only specific pages from a PDF:

```bash
# Pages 1 through 5
python read_aloud.py book.pdf --pages 1-5

# Pages 1-3, 7, and 10-12
python read_aloud.py book.pdf --pages 1-3,7,10-12
```

The `--pages` flag is only valid for PDF files.

### Paragraph range

Read only a subset of paragraphs (after parsing and splitting):

```bash
# Read paragraphs 5 through 10
python read_aloud.py document.pdf --start 5 --end 10

# Read from paragraph 20 onward
python read_aloud.py document.pdf --start 20
```

Combine with `--dry-run` to preview which paragraphs fall in the range.

### Read an EPUB

```bash
python read_aloud.py novel.epub --voice jean
```

Requires `ebooklib` and `beautifulsoup4`. Text is extracted from all HTML content documents in the EPUB, pulling text from `<p>` and heading tags.

### Device selection

List available audio output devices:

```bash
python read_aloud.py --list-devices
```

Select a specific device by index or name:

```bash
# By index
python read_aloud.py document.pdf --device 3

# By name substring (case-insensitive)
python read_aloud.py document.pdf --device "headphones"
```

### List voices from server

Query the running TTS server for its available voices:

```bash
python read_aloud.py --list-voices
python read_aloud.py --list-voices --uri tcp://192.168.1.50:10201
```

### Batch mode

Read multiple files in sequence:

```bash
python read_aloud.py chapter1.pdf chapter2.pdf chapter3.pdf

# With WAV output — auto-generates chapter1.wav, chapter2.wav, chapter3.wav
python read_aloud.py chapter1.pdf chapter2.pdf chapter3.pdf -o output.wav
```

When `--output` is specified with multiple files, each file's audio is saved using the file's stem name in the output directory (e.g., `chapter1.wav`, `chapter2.wav`).

### Debug mode

Enable debug logging to see detailed synthesis information:

```bash
python read_aloud.py document.md --debug
```

Debug output goes to stderr via Rich's log handler, with colored tracebacks and timestamps.

## Interactive Controls

During playback, the following keyboard controls are available (when running in a terminal):

| Key | Action |
|---|---|
| `Space` or `p` | Toggle pause/resume |
| `n` | Skip to next paragraph |
| `q` | Quit playback |

Controls are shown at the bottom of the live status display. They are automatically disabled when stdin is not a TTY (e.g., when piping input).

## Config File

Save your preferred defaults to `~/.read_aloud.toml` so you don't have to type them every time:

```bash
# Save current flags as defaults
python read_aloud.py --save-config --voice cosette --uri tcp://192.168.1.50:10201

# Subsequent runs use saved defaults
python read_aloud.py document.pdf  # uses voice=cosette, uri=tcp://192.168.1.50:10201
```

The config file uses TOML format:

```toml
[defaults]
voice = "cosette"
uri = "tcp://192.168.1.50:10201"
device = "headphones"
```

CLI arguments always override config file values.

Requires `tomllib` (Python 3.11+ stdlib) or the `tomli` package (Python 3.10).

## How It Works

### Document Parsing

The tool extracts readable text from the input file and splits it into paragraphs:

- **PDF** (`.pdf`): Extracts text from each page using PyMuPDF. Splits on double-newlines to form paragraphs. Whitespace is normalized. Supports `--pages` to limit which pages are read.
- **DOCX** (`.docx`): Iterates over the document's paragraph objects. Empty paragraphs are filtered out.
- **EPUB** (`.epub`): Uses `ebooklib` to read EPUB content documents and `BeautifulSoup` to extract text from `<p>` and heading tags.
- **Markdown / Text** (`.md`, `.markdown`, `.txt`): Strips markdown syntax — headings, bold/italic markers, links, images, code blocks, list markers, blockquotes, and horizontal rules — then splits on double-newlines.

Long paragraphs (over 500 characters) are automatically split at sentence boundaries (`.`, `!`, `?`) to avoid overwhelming the TTS engine.

### Synthesis and Playback

For each paragraph, the tool:

1. Opens a TCP connection to the Wyoming TTS server
2. Sends a `Synthesize` event with the paragraph text and selected voice
3. Receives `AudioStart` (format metadata), one or more `AudioChunk` events (PCM audio data), and `AudioStop`
4. Plays the received PCM audio through your speakers using `sounddevice` in ~100ms chunks for responsive interactive controls
5. Accumulates the audio data for optional WAV export

A live status display shows current progress, elapsed time, and estimated remaining time:

```
[3/12]  Elapsed: 1:23  Remaining: 4:15
  This report summarizes the quarterly results for the fiscal year ending...
  [space] pause  [n] next  [q] quit
```

If a paragraph fails to synthesize (server error, connection issue), the error is printed and playback continues with the next paragraph.

### WAV Export

After all paragraphs have been read aloud, the tool either:

- **Saves automatically** if `--output` / `-o` was specified
- **Prompts interactively** asking whether to save, and if so, what filename to use (defaults to `<input_stem>.wav`)

The WAV file contains the concatenated audio from all successfully synthesized paragraphs, in the server's native format (typically 24kHz, 16-bit, mono).

## Supported File Types

| Extension | Parser | Notes |
|---|---|---|
| `.pdf` | PyMuPDF | Text-based PDFs only; scanned/image PDFs will produce no text. Supports `--pages`. |
| `.docx` | python-docx | Microsoft Word Open XML format |
| `.epub` | ebooklib + BeautifulSoup | EPUB e-books; extracts text from HTML content |
| `.md` | Regex-based | GitHub-flavored Markdown syntax is stripped |
| `.markdown` | Regex-based | Same as `.md` |
| `.txt` | Regex-based | Treated as plain text / lightweight Markdown |

## Troubleshooting

### "Cannot connect to TTS server"

The tool cannot reach the Wyoming server. Check that:

- The server is running (`docker compose up` or running `wyoming_tts_server.py` directly)
- The URI is correct (default: `tcp://localhost:10201`)
- No firewall is blocking the port
- If using Docker, the port is mapped to the host

### "No text found in file"

The document parser found no readable text. Common causes:

- The PDF is a scanned image (not text-based). Use OCR to convert it first.
- The DOCX file contains only images or embedded objects.
- The EPUB contains no `<p>` or heading tags in its content documents.
- The file is empty.

### No audio output / silence

- Check that your system audio output device is working
- Use `--list-devices` to verify your output device is detected
- Try specifying a device explicitly with `--device`
- Try playing a test sound: `python -c "import sounddevice as sd; import numpy as np; sd.play(np.sin(np.linspace(0,1000,24000)).astype('float32'), 24000); sd.wait()"`
- On Linux, ensure PortAudio is installed: `sudo apt install libportaudio2`

### Interactive controls not working

- Controls only work when stdin is a TTY (interactive terminal)
- They are disabled when piping input or running in non-interactive environments
- On Windows, the tool uses `msvcrt` for key detection
- On Linux/macOS, the tool uses `tty`/`termios` with `select`

### Individual paragraphs fail but others succeed

This is expected behavior. The tool logs the error for the failed paragraph and continues with the rest. Use `--debug` to see the full error traceback. Common causes include text that the TTS model can't handle (unusual characters, extremely long words).
