#!/usr/bin/env python3
"""Mac-side processor v2: transcribe + index, fully local RAG pipeline.

Stage 1 (transcribe): DONE, no TRANSCRIBED -> Whisper (MLX) -> transcript.txt + segments.json
Stage 2 (index):      TRANSCRIBED, no INDEXED -> chunk -> embed (Ollama) -> Chroma vector DB

Nothing leaves this machine.
"""

import json
import subprocess
import time
from pathlib import Path

import chromadb
import mlx_whisper
import ollama

WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
EMBED_MODEL = "nomic-embed-text"
BASE_DIR = Path.home() / "Workspace/transcriber"
RECORDINGS_DIR = BASE_DIR / "recordings"
DB_DIR = BASE_DIR / "chroma"
POLL_SECONDS = 5
CHUNK_WORDS = 180  # roughly a minute of speech per searchable chunk

db = chromadb.PersistentClient(path=str(DB_DIR))
collection = db.get_or_create_collection("sessions")


def build_session_wav(session: Path) -> Path:
    """Join all chunks into one loudness-normalized session.wav."""
    chunks = sorted(session.glob("chunk-*.wav"))
    listfile = session / "chunks.txt"
    listfile.write_text("".join(f"file '{c}'\n" for c in chunks))
    out = session / "session.wav"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(listfile),
            "-af", "loudnorm",
            "-ar", "16000",
            str(out),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    listfile.unlink()
    return out


def transcribe(session: Path) -> None:
    wav = build_session_wav(session)
    result = mlx_whisper.transcribe(str(wav), path_or_hf_repo=WHISPER_MODEL)

    (session / "transcript.txt").write_text(result["text"].strip() + "\n")

    segments = [
        {"start": round(s["start"], 2), "end": round(s["end"], 2), "text": s["text"].strip()}
        for s in result["segments"]
    ]
    (session / "segments.json").write_text(json.dumps(segments, indent=2))

    (session / "TRANSCRIBED").touch()
    print(f"PROCESSED {session.name}: {len(segments)} segments", flush=True)


def chunk_segments(segments: list) -> list:
    """Group whisper segments into ~CHUNK_WORDS-word chunks, keeping timestamps."""
    groups, current, words = [], [], 0
    for seg in segments:
        current.append(seg)
        words += len(seg["text"].split())
        if words >= CHUNK_WORDS:
            groups.append(current)
            current, words = [], 0
    if current:
        groups.append(current)
    return groups


def index(session: Path) -> None:
    segments = json.loads((session / "segments.json").read_text())
    docs, ids, metas = [], [], []
    for i, group in enumerate(chunk_segments(segments)):
        text = " ".join(s["text"] for s in group).strip()
        if not text:
            continue
        docs.append(text)
        ids.append(f"{session.name}-{i}")
        metas.append({
            "session": session.name,
            "start": group[0]["start"],
            "end": group[-1]["end"],
        })
    if docs:
        embeddings = ollama.embed(model=EMBED_MODEL, input=docs).embeddings
        collection.upsert(ids=ids, embeddings=embeddings, documents=docs, metadatas=metas)
    (session / "INDEXED").touch()
    print(f"INDEXED {session.name}: {len(docs)} chunks", flush=True)


def main() -> None:
    print(f"Watching {RECORDINGS_DIR} | whisper={WHISPER_MODEL} | embed={EMBED_MODEL}", flush=True)
    while True:
        if RECORDINGS_DIR.exists():
            for session in sorted(RECORDINGS_DIR.iterdir()):
                if not session.is_dir():
                    continue
                try:
                    if (session / "DONE").exists() and not (session / "TRANSCRIBED").exists():
                        transcribe(session)
                    if (session / "TRANSCRIBED").exists() and not (session / "INDEXED").exists():
                        index(session)
                except subprocess.CalledProcessError as exc:
                    print(f"ERROR {session.name}: ffmpeg: {exc.stderr[-300:]} (will retry)", flush=True)
                except Exception as exc:
                    print(f"ERROR {session.name}: {exc} (will retry)", flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
