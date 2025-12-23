#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export HOME="${HOME:-/root}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/obs-runtime}"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

DISPLAY="${OBS_DISPLAY:-:99}"
export DISPLAY

Xvfb "$DISPLAY" -screen 0 1920x1080x24 -nolisten tcp &
XVFB_PID=$!

if command -v pulseaudio >/dev/null 2>&1; then
  pulseaudio --check || pulseaudio --start --exit-idle-time=-1 || true
fi

"$ROOT_DIR/.venv/bin/python" -m vk_stream.prepare_obs

if ! command -v obs >/dev/null 2>&1; then
  echo "obs binary not found; install obs-studio" >&2
  exit 1
fi

obs --disable-shutdown-check --minimize-to-tray --no-splash &
OBS_PID=$!

cleanup() {
  kill "$OBS_PID" "$XVFB_PID" 2>/dev/null || true
}
trap cleanup EXIT

exec "$ROOT_DIR/.venv/bin/python" -m vk_stream
