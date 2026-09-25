#!/usr/bin/env bash
# Install the recorder + uploader on a Raspberry Pi (Raspberry Pi OS Bookworm).
# Run as the user who will own the recordings, from a clone of this repo:
#   ./pi/install.sh
set -euo pipefail

PI_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_USER="$(id -un)"
RUN_HOME="$HOME"
BOOT_CONFIG=/boot/firmware/config.txt

if [[ "$RUN_USER" == "root" ]]; then
  echo "Run as your normal user, not root (sudo is used where needed)." >&2
  exit 1
fi

if [[ ! -f "$PI_DIR/.env" ]]; then
  echo "Missing $PI_DIR/.env. Copy .env.example to .env and fill it in first." >&2
  exit 1
fi

render() {
  sed -e "s|__USER__|$RUN_USER|g" \
      -e "s|__HOME__|$RUN_HOME|g" \
      -e "s|__PI_DIR__|$PI_DIR|g" "$1"
}

echo "==> Installing packages"
sudo apt-get update -qq
sudo apt-get install -y python3-gpiozero alsa-utils rsync

echo "==> Installing sudoers rule for shutdown"
tmp="$(mktemp)"
render "$PI_DIR/config/sudoers.d/recorder-shutdown" > "$tmp"
sudo visudo -cf "$tmp"
sudo install -m 0440 -o root -g root "$tmp" /etc/sudoers.d/recorder-shutdown
rm -f "$tmp"

echo "==> Installing systemd services"
for unit in recorder.service uploader.service; do
  render "$PI_DIR/systemd/$unit" | sudo tee "/etc/systemd/system/$unit" > /dev/null
done
sudo systemctl daemon-reload
sudo systemctl enable recorder.service uploader.service
sudo systemctl restart recorder.service uploader.service

echo "==> Checking $BOOT_CONFIG"
missing=0
while IFS= read -r line; do
  [[ -z "$line" || "$line" == \#* || "$line" == \[* ]] && continue
  if ! grep -qxF "$line" "$BOOT_CONFIG"; then
    echo "   missing: $line"
    missing=1
  fi
done < "$PI_DIR/config/config.txt.snippet"
if (( missing )); then
  echo "   Add the lines above under [all] in $BOOT_CONFIG, then reboot."
else
  echo "   OK"
fi

echo
echo "Done. Check status with:"
echo "  systemctl status recorder uploader"
echo "  journalctl -u recorder -u uploader -f"
