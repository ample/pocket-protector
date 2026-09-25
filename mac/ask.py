#!/usr/bin/env python3
"""Ask questions of everything you've recorded. Fully local: Ollama + Chroma.

Usage:
    ask.py "what did we decide about the deck material?"
"""

import sys
from pathlib import Path

import chromadb
import ollama

CHAT_MODEL = "llama3.1:8b"
EMBED_MODEL = "nomic-embed-text"
DB_DIR = Path.home() / "Workspace/transcriber/chroma"
TOP_K = 6


def mmss(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def main() -> None:
    if len(sys.argv) < 2:
        print('usage: ask.py "your question"')
        sys.exit(1)
    question = " ".join(sys.argv[1:])

    collection = chromadb.PersistentClient(path=str(DB_DIR)).get_or_create_collection("sessions")
    q_emb = ollama.embed(model=EMBED_MODEL, input=[question]).embeddings
    res = collection.query(query_embeddings=q_emb, n_results=TOP_K)

    docs = res["documents"][0]
    metas = res["metadatas"][0]
    if not docs:
        print("No indexed recordings yet.")
        return

    context = "\n\n".join(
        f"[{m['session']} {mmss(m['start'])}-{mmss(m['end'])}]\n{d}"
        for d, m in zip(docs, metas)
    )
    prompt = (
        "Answer the question using only the transcript excerpts below. "
        "Cite the session name and timestamp range for anything you use. "
        "If the excerpts don't contain the answer, say so plainly.\n\n"
        f"EXCERPTS:\n{context}\n\nQUESTION: {question}"
    )

    resp = ollama.chat(model=CHAT_MODEL, messages=[{"role": "user", "content": prompt}])
    print("\n" + resp.message.content.strip() + "\n")
    print("Sources searched:")
    for m in metas:
        print(f"  {m['session']}  {mmss(m['start'])}-{mmss(m['end'])}")


if __name__ == "__main__":
    main()
