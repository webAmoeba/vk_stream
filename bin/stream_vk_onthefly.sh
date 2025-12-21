#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source ./.env

: "${RTMP_URL:?Set RTMP_URL in .env}"
: "${STREAM_KEY:?Set STREAM_KEY in .env}"
: "${VIDEO_DIR:?Set VIDEO_DIR in .env}"
: "${AUDIO_INDEX:?Set AUDIO_INDEX (e.g. 1) in .env}"
: "${SUB_SI:?Set SUB_SI (e.g. 1) in .env}"

OUT="${RTMP_URL}/${STREAM_KEY}"

# Опционально (можно задать в .env):
# START_EP="S01E04"            # начать с этого файла (без .mkv), только первый круг
# BETWEEN_FILES_SLEEP=0        # пауза между файлами (сек), по умолчанию 0
START_EP="${START_EP:-}"
BETWEEN_FILES_SLEEP="${BETWEEN_FILES_SLEEP:-0}"
started_once=0

NOW_FILE="/root/repos/vk_stream/nowplaying.txt"
FONT_FILE="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

while true; do
  # Собираем список файлов в "естественном" порядке (S01E01, S01E02 ... S10E01 ...)
  mapfile -d '' files < <(
    find "$VIDEO_DIR" -type f -iname "*.mkv" -print0 | sort -zV
  )

  if [[ ${#files[@]} -eq 0 ]]; then
    echo "No .mkv files found under VIDEO_DIR=$VIDEO_DIR" >&2
    sleep 10
    continue
  fi

  # Старт с нужного эпизода только один раз (первый проход)
  if [[ -n "$START_EP" && $started_once -eq 0 ]]; then
    idx=-1
    for i in "${!files[@]}"; do
      base="$(basename "${files[$i]}" .mkv)"
      if [[ "$base" == "$START_EP" ]]; then
        idx=$i
        break
      fi
    done

    if [[ $idx -ge 0 ]]; then
      files=( "${files[@]:$idx}" "${files[@]:0:$idx}" )
      echo "Starting from episode: $START_EP"
    else
      echo "WARN: START_EP not found: $START_EP" >&2
    fi
    started_once=1
  fi

  for f in "${files[@]}"; do
    echo "==> streaming: $f"

    # Обновляем "сейчас играет" (атомарно, чтобы drawtext не прочитал кусок файла)
    title="$(basename "$f" .mkv)"
    printf '%s\n' "$title" > "${NOW_FILE}.tmp"
    mv -f "${NOW_FILE}.tmp" "$NOW_FILE"

    if ffmpeg -hide_banner -loglevel info -re -i "$f" \
      -map 0:v:0 -map "0:a:${AUDIO_INDEX}" \
      -vf "subtitles=${f}:si=${SUB_SI},drawtext=fontfile=${FONT_FILE}:textfile=${NOW_FILE}:reload=1:x=20:y=20:fontsize=36:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=10" \
      -c:v libx264 -preset veryfast -pix_fmt yuv420p -g 60 \
      -c:a aac -b:a 128k -ar 44100 -ac 2 \
      -f flv "$OUT"
    then
      :
    else
      rc=$?
      echo "ffmpeg failed (rc=$rc) on: $f" >&2
    fi

    sleep "$BETWEEN_FILES_SLEEP"
  done
done
