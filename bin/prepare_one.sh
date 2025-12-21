#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source ./.env

in="${1:?usage: prepare_one.sh /path/to/input.mkv}"
rel="${in#${VIDEO_DIR}/}"
out="${PREPARED_DIR}/${rel%.*}.mp4"

mkdir -p "$(dirname "$out")"

ffmpeg -y -i "$in" \
  -map 0:v:0 -map 0:a:m:language:${AUDIO_LANG}? \
  -vf "subtitles=${in}:si=${SUB_SI}" \
  -c:v libx264 -preset veryfast -crf 20 \
  -c:a aac -b:a 128k \
  "$out"
