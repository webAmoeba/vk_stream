vk_stream (24/7 VK RTMP из папки с видео)

Проект стримит видеофайлы по кругу в VK Live через RTMP. Один процесс FFmpeg читает concat-плейлист и транслирует без разрывов между файлами.

0) Требования
- Ubuntu 24.04 (root или sudo)
- ffmpeg
- make
- uv (будет установлен через make install)

1) Установка
Из корня проекта:
make install

2) Настройка .env
Скопируйте пример:
cp .env.example .env

Минимум:
RTMP_URL="rtmp://<vk-server>/live"
STREAM_KEY="<vk-key>"
VIDEO_DIR="/root/downloads/myVideos"
START_EP="S02E16"

Пояснения:
- VIDEO_DIR: корневая папка с сезонами/эпизодами.
- START_EP: начать с указанного эпизода (ищется по имени SxxEyy). При LOOP=1 плейлист будет циклично начинаться с этого эпизода.

Дополнительно (опционально):
- LOGLEVEL="info"
- LOOP=1
- VIDEO_EXTS=".mkv"
- PLAYLIST_PATH="var/playlist.txt"
- FFMPEG_PATH="ffmpeg"

Стрим c прожигом субтитров и названием (вариант Б):
- STREAM_SUB_BURN=1           # включить прожиг субтитров на лету (требует перекодирования видео)
- STREAM_SUB_SI=1             # индекс сабов (среди subtitle-стримов)
- STREAM_AUDIO_INDEX=1        # индекс аудио (среди audio-стримов)
- STREAM_DRAW_TEXT=1          # вывод названия поверх видео
- STREAM_TITLE_FILE="var/nowplaying.txt"
- STREAM_TITLE_MODE="stem"    # stem | episode
- STREAM_TITLE_DELAY=0        # задержка показа названия (сек)

Кодеки/битрейты для варианта Б:
- STREAM_VIDEO_CODEC="libx264"
- STREAM_VIDEO_BITRATE="4500k"
- STREAM_MAXRATE="6000k"
- STREAM_BUFSIZE="9000k"
- STREAM_PRESET="veryfast"
- STREAM_GOP=48
- STREAM_AUDIO_CODEC="aac"
- STREAM_AUDIO_BITRATE="160k"
- STREAM_AUDIO_RATE="48000"
- STREAM_AUDIO_CHANNELS=2

Низкая нагрузка (без субтитров и названия):
- STREAM_SUB_BURN=0
- STREAM_DRAW_TEXT=0
- STREAM_VIDEO_CODEC="copy"

3) Запуск
make start
make status
make logs

Автозапуск:
make enable
make disable

4) Полезные проверки
Проверить дорожки (на одном файле):
ffprobe -v error -select_streams a -show_entries stream=index:stream_tags=language,title -of csv=p=0 "file.mkv"
ffprobe -v error -select_streams s -show_entries stream=index:stream_tags=language,title -of csv=p=0 "file.mkv"

Сгенерировать плейлист вручную:
make gen

Заметки:
- Плейлист строится по файлам из VIDEO_DIR, сортировка по SxxEyy в названии.
- Если рядом есть файлы с одинаковым именем (SxxEyy), выбирается расширение по порядку VIDEO_EXTS.
- Для прожига субтитров используется отдельный плейлист `vk_stream_subs_playlist.txt` в VIDEO_DIR, он перезаписывается при каждом запуске.

5) Конвертация с прожигом субтитров (по одному файлу)
Цель: один раз подготовить файлы с вшитыми субтитрами и нужной аудиодорожкой.

Проверка одного файла (оригинал не удаляется):
make convert-one FILE=/path/to/file.mkv

Полная конвертация (по очереди, удаляет оригинал после успеха):
make convert-all

Настройки конвертации в .env (опционально):
- AUDIO_INDEX=1                # если задан, используется как дефолт для CONVERT_AUDIO_INDEX
- SUB_SI=1                     # если задан, используется как дефолт для CONVERT_SUB_SI
- CONVERT_AUDIO_INDEX=1
- CONVERT_SUB_SI=1
- CONVERT_SUB_BURN=1
- CONVERT_PRESET="veryfast"
- CONVERT_VBITRATE="5000k"
- CONVERT_MAXRATE="6000k"
- CONVERT_BUFSIZE="12000k"
- CONVERT_CRF=20
- CONVERT_AUDIO_BITRATE="160k"
- CONVERT_AUDIO_RATE="48000"
- CONVERT_AUDIO_CHANNELS=2
- CONVERT_SCALE=""             # оставить исходный размер
- CONVERT_OUT_EXT=".mp4"
- CONVERT_INPUT_EXTS=".mkv"
- CONVERT_OVERWRITE=0
