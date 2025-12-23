vk_stream — стример через OBS (VLC source + субтитры) в VK Live (RTMP)

Проект запускает OBS headless и управляет им через obs-websocket.
Файлы проигрываются по одному, субтитры видимые, название файла
в левом верхнем углу.

1) Требования
- Ubuntu 24.04
- obs-studio, vlc, ffmpeg, xvfb, pulseaudio
- make
- uv (ставится через make install)

2) Установка
Из корня проекта:
make install

3) Настройка .env
Скопируйте пример:
cp .env.example .env

Минимум:
VK_URL="rtmp://<vk-server>/input/"
VK_KEY="<vk-key>"
VIDEO_DIR="/root/downloads/myVideos"
START_EP="S01E01"
OBS_PASSWORD="CHANGE_ME"

Опционально:
- OBS_HOST, OBS_PORT, OBS_SCENE, OBS_VLC_SOURCE, OBS_TEXT_SOURCE
- VIDEO_EXTS=".mkv"
- LOOP=1
- AUDIO_INDEX=1
- SUB_SI=1
- STREAM_VIDEO_BITRATE="3000k"
- STREAM_AUDIO_BITRATE="160k"
- STREAM_PRESET="superfast"

4) Запуск
make start
make status
make logs

5) Заметки
- OBS запускается через Xvfb, управление — через obs-websocket.
- START_EP влияет только на первый запуск цикла.
  Когда дойдёт до последнего файла, новый круг начнётся с первого.
- Если START_EP не найден, начнётся с первого файла.
- Название файла выводится в левом верхнем углу (формат S01E01).
- AUDIO_INDEX / SUB_SI применяются к VLC source; при необходимости подберите индекс.
