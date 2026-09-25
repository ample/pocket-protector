#!/usr/bin/env python3
"""Pocket uploader: ships finished recording sessions to the Mac Mini over Tailscale.

Watches ~/recordings/ for session folders containing a DONE marker and
rsyncs them to DEST. Audio chunks ship first; the DONE marker ships last,
so the Mac never sees a session marked complete before all audio arrived.
Writes a local UPLOADED marker on success. Safe to re-run: uploaded
sessions are skipped, failed sessions retry on the next pass.
"""

import os
import subprocess
import time
from pathlib import Path

# Set in pi/.env (loaded by uploader.service via EnvironmentFile).
DEST = f"{os.environ['MAC_USER']}@{os.environ['MAC_HOST']}:{os.environ['MAC_RECORDINGS_DIR']}"

RECORDINGS_DIR = Path.home() / "recordings"
POLL_SECONDS = 5


def rsync(*args: str) -> None:
    subprocess.run(
        ["rsync", "-a", "--partial", "-e", "ssh -o BatchMode=yes", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def upload_session(session: Path) -> None:
    remote = f"{DEST}/{session.name}/"
    # 1) ship the audio
    rsync("--exclude", "DONE", "--exclude", "UPLOADED", f"{session}/", remote)
    # 2) ship the DONE marker last = arrival receipt for the Mac side
    rsync(str(session / "DONE"), remote)
    (session / "UPLOADED").touch()
    n = len(list(session.glob("chunk-*.wav")))
    print(f"UP  {session.name} ({n} chunks) -> {remote}", flush=True)


def main() -> None:
    print(f"Watching {RECORDINGS_DIR} -> {DEST}", flush=True)
    while True:
        if RECORDINGS_DIR.exists():
            for session in sorted(RECORDINGS_DIR.iterdir()):
                if not session.is_dir():
                    continue
                if (session / "DONE").exists() and not (session / "UPLOADED").exists():
                    try:
                        upload_session(session)
                    except subprocess.CalledProcessError as exc:
                        detail = exc.stderr.strip() if exc.stderr else exc
                        print(f"ERROR {session.name}: rsync failed: {detail} (will retry)", flush=True)
                    except Exception as exc:
                        print(f"ERROR {session.name}: {exc} (will retry)", flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
