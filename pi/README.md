# Pi (recorder)

The Raspberry Pi listens for control pulses from the [controller](../controller/), records audio in chunks, and hands finished sessions to the Mac.

> **Status:** scaffold. Pi-side files still need to be added from the device.

## Layout

| Path | Contents |
|---|---|
| `recorder.py` | GPIO listener + chunked recorder (to add) |
| `systemd/` | `.service` / `.timer` units you created under `/etc/systemd/system/` |
| `config/` | Only the lines you changed in `config.txt`, plus ALSA/mic config if customized |
| `install.sh` | Copies files into place and enables services (to add) |
| `requirements.txt` | Pi Python dependencies (to add) |
| `.env.example` | Template for host-specific settings; copy to `.env` (git-ignored) |

## Control input

Pi physical pin 10 (GPIO15) receives open-drain LOW pulses from the ESP32. Enable the Pi's internal pull-up on this pin.

| Pulse length | Meaning |
|---|---|
| ~150 ms | Toggle recording |
| ~1200 ms | Shut down (`sudo shutdown -h now`). Power is cut 15 s later. |

Pin 10 is also UART RX. Disable the serial console and UART (for example, `enable_uart=0` in `config.txt` and remove `console=serial0,...` from `cmdline.txt`), or it will conflict with the control line.

## Output contract

The Mac's [processor](../mac/) depends on this format:

```
recordings/YYYYMMDD-HHMMSS/        # one folder per session, named by start time
├── chunk-HHMMSS-01.wav            # ~1-minute chunks, named by chunk start time + sequence
├── chunk-HHMMSS-02.wav
└── DONE                           # written last, after the final chunk is closed
```

Only write `DONE` once every chunk is fully flushed **and synced** to the Mac. The processor starts as soon as it sees the marker.

## Sync to the Mac

TODO: document how sessions get to `~/Workspace/transcriber/recordings/` (rsync, Syncthing, etc.).

## Don't commit

SSH keys, Wi-Fi config (`wpa_supplicant.conf`, NetworkManager connections), Tailscale or other auth, and Syncthing config (device IDs and keys). Hostnames, users, and IPs go in `.env`.
