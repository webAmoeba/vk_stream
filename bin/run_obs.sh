#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/obs-runtime}"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

if command -v pulseaudio >/dev/null 2>&1; then
  pulseaudio --check || pulseaudio --start --exit-idle-time=-1 || true
fi

"$ROOT_DIR/.venv/bin/python" -m vk_stream.prepare_obs

DISPLAY="${OBS_DISPLAY:-:99}"
Xvfb "$DISPLAY" -screen 0 1920x1080x24 -nolisten tcp &
XVFB_PID=$!
export DISPLAY

obs --disable-shutdown-check --minimize-to-tray --no-splash &
OBS_PID=$!

cleanup() {
  kill "$OBS_PID" "$XVFB_PID" 2>/dev/null || true
}
trap cleanup EXIT

exec "$ROOT_DIR/.venv/bin/python" -m vk_stream
