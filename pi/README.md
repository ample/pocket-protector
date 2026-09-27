# Pi (recorder)

The Raspberry Pi listens for control pulses from the [controller](../controller/), records audio in 1-minute chunks, and uploads finished sessions to the Mac over Tailscale.

## Layout

| Path | Contents |
|---|---|
| `recorder.py` | GPIO15 pulse listener; runs `arecord` in 1-minute chunks and writes `DONE` |
| `uploader.py` | rsyncs finished sessions to the Mac and writes a local `UPLOADED` marker |
| `systemd/` | Unit templates for both services (`__USER__` etc. are filled in by `install.sh`) |
| `config/config.txt.snippet` | The lines added to `/boot/firmware/config.txt` |
| `config/sudoers.d/recorder-shutdown` | Lets the recorder run `shutdown -h now` without a password |
| `install.sh` | Installs packages, the sudoers rule, and the services |
| `.env.example` | Template for the upload destination; copy to `.env` (git-ignored) |

## Hardware

- **Mic:** INMP441 I2S MEMS mic, driven by the `googlevoicehat-soundcard` overlay. It appears as ALSA card `sndrpigooglevoi`; check with `arecord -l`.
- **Control input:** physical pin 10 (BCM GPIO15), with an internal pull-up, receiving open-drain LOW pulses from the ESP32.
- **Status outputs to the ESP32** (which drives the button LED):
  - Physical pin 13 (BCM GPIO27): HIGH while recording.
  - Physical pin 11 (BCM GPIO17): HIGH while `recorder.py` is running and ready. It drops when a shutdown starts or the service stops.

| Pulse length | Meaning |
|---|---|
| 0.05–0.70 s (ESP32 sends ~150 ms) | Toggle recording |
| ≥0.90 s (ESP32 sends ~1200 ms) | Stop any recording, write `DONE`, then `shutdown -h now`. The ESP32 cuts power 15 s later. |

Pin 10 is also UART RX, which is why `config.txt` sets `enable_uart=0`. `cmdline.txt` must not contain `console=serial0,...`. A stock Bookworm install only uses `console=tty1`.

## Setup

1. **Boot config:** add the lines from [`config/config.txt.snippet`](config/config.txt.snippet) under `[all]` in `/boot/firmware/config.txt`, then reboot.
2. **Tailscale:** install and log in on both the Pi and the Mac.
3. **SSH to the Mac:** the uploader uses `ssh -o BatchMode=yes`, so it needs key auth.
   - On the Mac: System Settings → General → Sharing → turn on **Remote Login**.
   - On the Pi: `ssh-keygen -t ed25519` (if you don't have a key), then `ssh-copy-id <mac-user>@<mac-host>`.
   - Test with `ssh -o BatchMode=yes <mac-user>@<mac-host> true`.
4. **Configure:** `cp pi/.env.example pi/.env` and fill in the Mac user, host, and recordings path.
5. **Install:** from the repo clone on the Pi, run `./pi/install.sh`.

Logs: `journalctl -u recorder -u uploader -f`

## Output contract

Sessions are recorded to `~/recordings/` on the Pi:

```
~/recordings/YYYYMMDD-HHMMSS/   # named by the Pi's clock at record start
├── chunk-HHMMSS-01.wav         # arecord --max-file-time 60, 16 kHz mono S16_LE
├── chunk-HHMMSS-02.wav
├── DONE                        # written after arecord exits
└── UPLOADED                    # Pi-only; written after a successful upload
```

## Sync to the Mac

`uploader.py` polls every 5 s for sessions that have `DONE` but not `UPLOADED`. For each one, it:

1. rsyncs the audio, excluding the `DONE` and `UPLOADED` markers
2. rsyncs `DONE` on its own, **last**

The Mac's [processor](../mac/) therefore never sees `DONE` before all the audio has arrived. Failed uploads retry on the next pass.

## Known limitations

- Uploaded sessions are never deleted from the Pi, so the SD card will fill up over time.
- The Pi has no real-time clock. Sessions recorded before it syncs time over the network can get wrong timestamps in their names.

## Don't commit

SSH keys, Wi-Fi config (`wpa_supplicant.conf`, NetworkManager connections), Tailscale auth, and `pi/.env`.
