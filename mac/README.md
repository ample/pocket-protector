# Mac (processing + query)

Transcribes and indexes sessions delivered by the [Pi](../pi/), then answers questions over them. Everything runs locally on Apple Silicon.

## Setup

```bash
brew install ffmpeg ollama
ollama pull nomic-embed-text
ollama pull llama3.1:8b

python3 -m venv env
source env/bin/activate
pip install -r mac/requirements.txt
```

Paths are hardcoded to `~/Workspace/transcriber` (`BASE_DIR` in `processor.py`, `DB_DIR` in `ask.py`). Edit them if you cloned the repo elsewhere.

## processor.py

A daemon that polls `recordings/` every 5 s. It uses marker files as its state machine:

1. **`DONE`, no `TRANSCRIBED`:** ffmpeg concatenates the chunks, applies `loudnorm`, and resamples to 16 kHz → `session.wav`. Whisper (`mlx-community/whisper-large-v3-turbo`) then writes `transcript.txt` and timestamped `segments.json`, and the `TRANSCRIBED` marker is added.
2. **`TRANSCRIBED`, no `INDEXED`:** segments are grouped into ~180-word chunks with start/end times. They're embedded with `nomic-embed-text` via Ollama and upserted into the Chroma collection `sessions` in `chroma/`. Then the `INDEXED` marker is added.

Failures are logged and retried on the next poll. To reprocess a session, delete its marker file(s).

```bash
python mac/processor.py
```

## ask.py

Embeds the question and retrieves the 6 nearest chunks. `llama3.1:8b` then answers from those excerpts only, citing session and `m:ss` ranges.

```bash
python mac/ask.py "what did we decide about the deck material?"
```
