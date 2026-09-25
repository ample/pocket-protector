#!/usr/bin/env python3

import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path

from gpiozero import Button, LED


MIC_DEVICE = "plughw:sndrpigooglevoi"
RECORDINGS_DIR = Path.home() / "recordings"
CHUNK_SECONDS = 60

# ESP32 signal line:
# Raspberry Pi physical pin 10 = BCM GPIO15
SIGNAL_GPIO = 15

# Existing recording indicator LED
LED_GPIO = 27

# Pulse lengths sent by the ESP32:
# ~0.150 s = record toggle
# ~1.200 s = shutdown request
SHORT_PULSE_MIN = 0.05
SHORT_PULSE_MAX = 0.70
SHUTDOWN_PULSE_MIN = 0.90


signal_line = Button(
    SIGNAL_GPIO,
    pull_up=True,
    bounce_time=0.01,
)

led = LED(LED_GPIO)

record_proc = None
session_dir = None
pressed_at = None
shutting_down = False


def start_recording():
    global record_proc, session_dir

    if record_proc is not None and record_proc.poll() is None:
        print("Already recording.", flush=True)
        return

    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

    session_dir = RECORDINGS_DIR / datetime.now().strftime("%Y%m%d-%H%M%S")
    session_dir.mkdir(parents=True, exist_ok=True)

    output_pattern = session_dir / "chunk-%H%M%S-%v.wav"

    cmd = [
        "arecord",
        "-D", MIC_DEVICE,
        "-f", "S16_LE",
        "-c", "1",
        "-r", "16000",
        "--max-file-time", str(CHUNK_SECONDS),
        "--use-strftime",
        str(output_pattern),
    ]

    print(f"Starting recording: {session_dir}", flush=True)

    record_proc = subprocess.Popen(cmd)

    led.on()


def stop_recording():
    global record_proc, session_dir

    if record_proc is None or record_proc.poll() is not None:
        record_proc = None
        led.off()
        print("Not currently recording.", flush=True)
        return

    print("Stopping recording...", flush=True)

    record_proc.send_signal(signal.SIGINT)

    try:
        record_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        print("arecord did not stop; terminating...", flush=True)
        record_proc.terminate()

        try:
            record_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            print("arecord still did not stop; killing...", flush=True)
            record_proc.kill()
            record_proc.wait()

    record_proc = None
    led.off()

    if session_dir is not None:
        done_file = session_dir / "DONE"
        done_file.touch()
        print(f"Recording complete: {session_dir}", flush=True)
        print(f"Created: {done_file}", flush=True)


def toggle_recording():
    if record_proc is not None and record_proc.poll() is None:
        stop_recording()
    else:
        start_recording()


def request_shutdown():
    global shutting_down

    if shutting_down:
        return

    shutting_down = True
    print("Shutdown requested.", flush=True)

    # Finish the current WAV and create DONE before Linux shuts down.
    if record_proc is not None and record_proc.poll() is None:
        stop_recording()

    # Give the filesystem a brief moment after finalizing the session.
    time.sleep(0.5)

    print("Shutting down Raspberry Pi...", flush=True)

    # This is intentionally non-interactive.
    # A narrow sudoers rule will permit only this shutdown command.
    result = subprocess.run(
        ["/usr/bin/sudo", "-n", "/usr/sbin/shutdown", "-h", "now"],
        check=False,
    )

    if result.returncode != 0:
        print(
            "Shutdown command failed. Check the recorder-shutdown sudoers rule.",
            flush=True,
        )
        shutting_down = False


def on_signal_pressed():
    global pressed_at
    pressed_at = time.monotonic()


def on_signal_released():
    global pressed_at

    if pressed_at is None:
        return

    duration = time.monotonic() - pressed_at
    pressed_at = None

    if SHORT_PULSE_MIN <= duration < SHORT_PULSE_MAX:
        print(f"RECORD_TOGGLE ({duration:.3f}s)", flush=True)
        toggle_recording()

    elif duration >= SHUTDOWN_PULSE_MIN:
        print(f"SHUTDOWN_REQUEST ({duration:.3f}s)", flush=True)
        request_shutdown()

    else:
        print(f"Ignored signal pulse ({duration:.3f}s)", flush=True)


def cleanup(*_args):
    print("Recorder exiting.", flush=True)

    if record_proc is not None and record_proc.poll() is None:
        stop_recording()

    led.off()
    raise SystemExit(0)


signal_line.when_pressed = on_signal_pressed
signal_line.when_released = on_signal_released

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

led.off()

print(
    "Recorder ready on BCM GPIO15 / physical pin 10.",
    flush=True,
)
print(
    "Single click toggles recording; long press requests shutdown.",
    flush=True,
)

signal.pause()
