# Transcriber

A push-button voice recorder with searchable, fully local memory. Press a button to record, and the audio is transcribed, indexed, and made queryable with a local LLM. Nothing leaves your machines.

```
[Button] → ESP32-C3 → Raspberry Pi (records chunks) → recordings/<session>/ on Mac
                                                          │
                                   processor.py (polls every 5s)
                                   1. ffmpeg: concat + loudnorm → session.wav
                                   2. Whisper (MLX) + pyannote speakers → transcript.txt + segments.json
                                   3. Ollama embeddings → Chroma vector DB
                                                          │
                          ask.py "question" → top-6 retrieval → llama3.1:8b answer with citations
```

## Repo layout

The repo is organized by where the code runs.

| Directory | Runs on | What it does |
|---|---|---|
| [`controller/`](controller/) | ESP32-C3 | Button gestures, status LED, record/shutdown pulses to the Pi, PowerBoost power control |
| [`pi/`](pi/) | Raspberry Pi | Records chunked audio sessions and syncs them to the Mac |
| [`mac/`](mac/) | Mac (Apple Silicon) | Transcribes, indexes, and answers questions |
| [`hardware/`](hardware/) | 3D printer | Enclosure files and parts list |
| [`site/`](site/) | Any static host | Setup microsite: a step-by-step build guide |

Each directory has its own README with setup steps.

## Session format (Pi → Mac contract)

```
recordings/YYYYMMDD-HHMMSS/
├── chunk-HHMMSS-NN.wav   # ~1-minute chunks, written by the Pi
├── DONE                  # Pi: recording finished and synced
├── session.wav           # Mac: concatenated + normalized
├── transcript.txt        # Mac: full text
├── segments.json         # Mac: [{start, end, speaker, text}, ...]
├── TRANSCRIBED           # Mac: stage 1 complete
└── INDEXED               # Mac: stage 2 complete
```

If you change this format on one side, update the other.

## Privacy

`recordings/` and `chroma/` (which stores transcript text) are git-ignored and never committed. So are `.env` files. Put hostnames and credentials there, and commit only the `.env.example` templates.
