# Transcriber

A push-button voice recorder with searchable, fully local memory. Press a button to record, and the audio is transcribed, indexed, and made queryable with a local LLM. Nothing leaves your machines.

```
[Button] → ESP32-C3 → Raspberry Pi (records chunks) → recordings/<session>/ on Mac
                                                          │
                                   processor.py (polls every 5s)
                                   1. ffmpeg: concat + loudnorm → session.wav
                                   2. Whisper (MLX) → transcript.txt + segments.json
                                   3. Ollama embeddings → Chroma vector DB
                                                          │
                          ask.py "question" → top-6 retrieval → llama3.1:8b answer with citations
```

## Components

| Path | What it is |
|---|---|
| `arduino-scripts/esp32_controller/` | ESP32-C3 firmware: button handling, Pi signaling, PowerBoost power control |
| `processor.py` | Mac-side daemon: transcribes and indexes finished sessions |
| `ask.py` | CLI for asking questions across all recordings |
| `fusion/` | 3D-printable enclosure files (`.3mf`) |

The Raspberry Pi recording script and the Pi-to-Mac sync live outside this repo.

## Hardware controller

An always-on ESP32-C3 Super Mini reads a single momentary button.

| Gesture | Action |
|---|---|
| Single click | 150 ms LOW pulse to the Pi: toggle recording |
| Triple click | Tap the PowerBoost K pin: power the Pi on |
| Long press (≥2.5 s, fires on release) | 1200 ms pulse to the Pi (shutdown), wait 15 s, double-tap K to cut 5V |

**Wiring**

- GPIO 4 → button → GND
- GPIO 5 → 1 kΩ → base of a 2N2222 that pulls the PowerBoost K pin to ground
- GPIO 3 → Raspberry Pi physical pin 10 (GPIO15). This line is open-drain, so the Pi is never back-powered.
- Common ground

Pi pin 10 is also UART RX, so disable the Pi's serial console and UART.

## Session lifecycle

Each recording is a folder `recordings/YYYYMMDD-HHMMSS/` of about 1-minute `chunk-HHMMSS-NN.wav` files. Marker files track progress:

1. `DONE`: written by the Pi when recording stops
2. `TRANSCRIBED`: `session.wav`, `transcript.txt`, and `segments.json` exist
3. `INDEXED`: ~180-word chunks with start/end timestamps are in the `sessions` Chroma collection

To reprocess a session, delete the relevant marker file(s). Failed steps are retried on every poll.

## Setup (Mac, Apple Silicon)

```bash
brew install ffmpeg ollama
ollama pull nomic-embed-text
ollama pull llama3.1:8b

python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```

Paths are hardcoded to `~/Workspace/transcriber`. If you clone the repo somewhere else, edit `BASE_DIR` / `DB_DIR`.

## Usage

Run the processor, and leave it running:

```bash
python processor.py
```

Ask a question:

```bash
python ask.py "what did we decide about the deck material?"
```

The answer cites the session name and a `m:ss` timestamp range, then lists the sources it searched.

## Models

- Transcription: `mlx-community/whisper-large-v3-turbo`
- Embeddings: `nomic-embed-text` (Ollama)
- Chat: `llama3.1:8b` (Ollama)

## Privacy

`recordings/` and `chroma/` (which stores transcript text) are git-ignored and never committed.
