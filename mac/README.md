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

Speaker labeling uses [`pyannote/speaker-diarization-3.1`](https://huggingface.co/pyannote/speaker-diarization-3.1). It's a gated model, so you have to download it once with a Hugging Face account. After that it runs offline.

1. Accept the terms on [speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) and [segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0).
2. Create a read token at huggingface.co/settings/tokens, then run `huggingface-cli login` (or export `HF_TOKEN`) before you first start `processor.py`.

`recordings/` and `chroma/` live at the project root, wherever you cloned the repo. The Pi's `MAC_RECORDINGS_DIR` must point at that `recordings/` folder.

## processor.py

A daemon that polls `recordings/` every 5 s. It uses marker files as its state machine:

1. **`DONE`, no `TRANSCRIBED`:** ffmpeg concatenates the chunks, applies `loudnorm`, and resamples to 16 kHz → `session.wav`. Whisper (`mlx-community/whisper-large-v3-turbo`) transcribes with word timestamps, and pyannote works out who spoke when. Each word goes to the speaker whose turn overlaps it most, and Whisper segments are split wherever the speaker changes. This writes `segments.json` (`{start, end, speaker, text}`) and `transcript.txt` (one `Speaker N: …` paragraph per turn), then adds the `TRANSCRIBED` marker. Speakers are numbered in order of first appearance within each session, so labels don't carry across sessions.
2. **`TRANSCRIBED`, no `INDEXED`:** segments are grouped into ~180-word chunks with start/end times and speaker-prefixed lines. They're embedded with `nomic-embed-text` via Ollama and upserted into the Chroma collection `sessions` in `chroma/`. The session's old chunks are deleted first. Then the `INDEXED` marker is added.

Failures are logged and retried on the next poll. To reprocess a session, delete its marker file(s). Sessions transcribed before speaker labeling was added need both `TRANSCRIBED` and `INDEXED` removed to pick up speakers:

```bash
rm recordings/*/TRANSCRIBED recordings/*/INDEXED
```

```bash
python mac/processor.py
```

### Transcription only

Set `SKIP_INDEXING=1` to stop after stage 1. You get `transcript.txt` and `segments.json`, with no Ollama, no Chroma, and no `chroma/` folder. You can skip the two `ollama pull` steps in Setup.

```bash
SKIP_INDEXING=1 python mac/processor.py
```

Sessions stay at `TRANSCRIBED`. Run without the variable later and they'll be indexed then.

## ask.py

Embeds the question and retrieves the 6 nearest chunks. `llama3.1:8b` then answers from those excerpts only, citing session and `m:ss` ranges.

```bash
python mac/ask.py "what did we decide about the deck material?"
```
