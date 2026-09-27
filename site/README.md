# Setup microsite

A static, five-page build guide for Pocket Protector: overview, hardware, Raspberry Pi, Mac, and record & ask. Plain HTML and one stylesheet, with no build step and no JavaScript.

| File | Page |
|---|---|
| `index.html` | Overview and how it works |
| `hardware.html` | 01 · Print, wire, and flash the controller |
| `pi.html` | 02 · Boot config, Tailscale, SSH, services |
| `mac.html` | 03 · Clone, models, pyannote unlock, processor |
| `use.html` | 04 · Gestures, session lifecycle, `ask.py`, troubleshooting |
| `assets/styles.css` | Shared styles and color tokens |
| `assets/logo.png` | Wordmark |

## Preview

```bash
python3 -m http.server 8000 --directory site
```

Then open http://localhost:8000.

## Deploy

Any static host works. Point it at `site/` with no build command.

## Keeping it accurate

The pages repeat facts from the device READMEs: pins, pulse timings, paths, and model names. If you change them in `controller/`, `pi/`, or `mac/`, update the matching page too.

Placeholders still to fill in:

- `[PI MODEL]` in `index.html` (the parts list)
- `[ADD MIC PIN MAP]` in `hardware.html` (Pi-side wiring)
