#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source ./.env

: "${RTMP_URL:?Set RTMP_URL in .env}"
: "${STREAM_KEY:?Set STREAM_KEY in .env}"

# бесконечный цикл по playlist.txt
ffmpeg -re \
  -stream_loop -1 -f concat -safe 0 -i playlist.txt \
  -c:v libx264 -preset veryfast -pix_fmt yuv420p -g 60 \
  -c:a aac -b:a 128k \
  -f flv "${RTMP_URL}/${STREAM_KEY}"
