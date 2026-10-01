#!/usr/bin/env python3
"""Mac-side processor v2: transcribe + index, fully local RAG pipeline.

Stage 1 (transcribe): DONE, no TRANSCRIBED -> Whisper (MLX) + pyannote diarization
                      -> transcript.txt + segments.json (with speaker labels)
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
import soundfile as sf
import torch
from pyannote.audio import Pipeline
from pyannote.audio.core.task import Problem, Resolution, Specifications

# torch>=2.6 defaults torch.load to weights_only=True; pyannote 3.x checkpoints
# pickle these classes, so allow exactly these rather than disabling the check.
torch.serialization.add_safe_globals([torch.torch_version.TorchVersion, Specifications, Problem, Resolution])

WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
DIARIZATION_MODEL = "pyannote/speaker-diarization-3.1"
EMBED_MODEL = "nomic-embed-text"
BASE_DIR = Path(__file__).resolve().parent.parent  # project root
RECORDINGS_DIR = BASE_DIR / "recordings"
DB_DIR = BASE_DIR / "chroma"
POLL_SECONDS = 5
CHUNK_WORDS = 180  # roughly a minute of speech per searchable chunk

db = chromadb.PersistentClient(path=str(DB_DIR))
collection = db.get_or_create_collection("sessions")
diarizer = None  # loaded in main(); slow to import and needs the HF model cached


def load_diarizer() -> Pipeline:
    """Load pyannote once. First run downloads the gated model, which needs a
    Hugging Face token (HF_TOKEN env var or `huggingface-cli login`)."""
    pipeline = Pipeline.from_pretrained(DIARIZATION_MODEL)
    if pipeline is None:
        raise SystemExit(
            f"Could not load {DIARIZATION_MODEL}. Accept its terms (and those of "
            "pyannote/segmentation-3.0) on huggingface.co, then set HF_TOKEN or run "
            "`huggingface-cli login`."
        )
    if torch.backends.mps.is_available():
        pipeline.to(torch.device("mps"))
    return pipeline


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


def diarize(wav: Path) -> list:
    """Return speaker turns as [(start, end, label), ...], labels like "Speaker 1"
    numbered in order of first appearance."""
    audio, sample_rate = sf.read(str(wav), dtype="float32", always_2d=True)
    waveform = torch.from_numpy(audio.T)
    annotation = diarizer({"waveform": waveform, "sample_rate": sample_rate})
    names, turns = {}, []
    for turn, _, raw in annotation.itertracks(yield_label=True):
        names.setdefault(raw, f"Speaker {len(names) + 1}")
        turns.append((turn.start, turn.end, names[raw]))
    return turns


def speaker_at(start: float, end: float, turns: list) -> str:
    """The speaker whose turn overlaps [start, end] most, else the nearest turn."""
    if not turns:
        return "Speaker 1"
    best, best_overlap = None, 0.0
    for t_start, t_end, label in turns:
        overlap = min(end, t_end) - max(start, t_start)
        if overlap > best_overlap:
            best, best_overlap = label, overlap
    if best:
        return best
    mid = (start + end) / 2
    return min(turns, key=lambda t: min(abs(mid - t[0]), abs(mid - t[1])))[2]


def label_segments(whisper_segments: list, turns: list) -> list:
    """Assign speakers per word, splitting whisper segments where the speaker changes."""
    segments = []
    for seg in whisper_segments:
        words = seg.get("words") or [{"word": seg["text"], "start": seg["start"], "end": seg["end"]}]
        run = None
        for w in words:
            speaker = speaker_at(w["start"], w["end"], turns)
            if run and run["speaker"] == speaker:
                run["end"] = w["end"]
                run["text"] += w["word"]
            else:
                run = {"start": w["start"], "end": w["end"], "speaker": speaker, "text": w["word"]}
                segments.append(run)
    for s in segments:
        s["start"], s["end"], s["text"] = round(s["start"], 2), round(s["end"], 2), s["text"].strip()
    return [s for s in segments if s["text"]]


def speaker_paragraphs(segments: list) -> list:
    """Merge consecutive same-speaker segments into "Speaker N: ..." lines."""
    lines = []
    for seg in segments:
        speaker = seg.get("speaker")
        if lines and lines[-1][0] == speaker:
            lines[-1][1].append(seg["text"])
        else:
            lines.append((speaker, [seg["text"]]))
    return [f"{spk}: {' '.join(texts)}" if spk else " ".join(texts) for spk, texts in lines]


def transcribe(session: Path) -> None:
    wav = build_session_wav(session)
    result = mlx_whisper.transcribe(str(wav), path_or_hf_repo=WHISPER_MODEL, word_timestamps=True)
    turns = diarize(wav)
    segments = label_segments(result["segments"], turns)

    (session / "transcript.txt").write_text("\n\n".join(speaker_paragraphs(segments)) + "\n")
    (session / "segments.json").write_text(json.dumps(segments, indent=2))

    (session / "TRANSCRIBED").touch()
    speakers = len({s["speaker"] for s in segments})
    print(f"PROCESSED {session.name}: {len(segments)} segments, {speakers} speaker(s)", flush=True)


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
        text = "\n".join(speaker_paragraphs(group)).strip()
        if not text:
            continue
        docs.append(text)
        ids.append(f"{session.name}-{i}")
        speakers = sorted({s["speaker"] for s in group if s.get("speaker")})
        metas.append({
            "session": session.name,
            "start": group[0]["start"],
            "end": group[-1]["end"],
            "speakers": ", ".join(speakers),
        })
    # Clear old chunks first: a reprocessed session may produce fewer of them.
    collection.delete(where={"session": session.name})
    if docs:
        embeddings = ollama.embed(model=EMBED_MODEL, input=docs).embeddings
        collection.upsert(ids=ids, embeddings=embeddings, documents=docs, metadatas=metas)
    (session / "INDEXED").touch()
    print(f"INDEXED {session.name}: {len(docs)} chunks", flush=True)


def main() -> None:
    global diarizer
    diarizer = load_diarizer()
    print(
        f"Watching {RECORDINGS_DIR} | whisper={WHISPER_MODEL} | "
        f"diarization={DIARIZATION_MODEL} | embed={EMBED_MODEL}",
        flush=True,
    )
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
