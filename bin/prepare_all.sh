#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source ./.env

find "$VIDEO_DIR" -type f -iname "*.mkv" -print0 | sort -zV | \
  while IFS= read -r -d '' f; do
    echo "==> $f"
    ./bin/prepare_one.sh "$f"
  done
