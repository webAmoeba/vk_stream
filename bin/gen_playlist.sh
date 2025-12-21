#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# .env — это shell-формат, можно source
source ./.env

: "${VIDEO_DIR:?Set VIDEO_DIR in .env}"

# concat demuxer: file 'path'
find "$VIDEO_DIR" -type f \( -iname "*.mp4" -o -iname "*.mkv" -o -iname "*.mov" \) -print0 \
| sort -z \
| xargs -0 -I{} printf "file '%s'\n" "{}" > playlist.txt

echo "OK: wrote $(wc -l < playlist.txt) entries to $(pwd)/playlist.txt"