vk_stream (24/7 VK RTMP из папки с .mkv)

Проект стримит .mkv файлы по кругу в VK Live через RTMP, выбирая нужную аудиодорожку и прожигая субтитры на лету (FFmpeg + libass). Один процесс FFmpeg читает concat-плейлист и транслирует без разрывов между файлами.

0) Требования
- Ubuntu 24.04 (root или sudo)
- ffmpeg
- make
- uv (будет установлен через make install)

1) Установка
Из корня проекта:
make install

2) Настройка .env
Пример:
RTMP_URL="rtmp://<vk-server>/live"
STREAM_KEY="<vk-key>"
VIDEO_DIR="/root/downloads/myVideos"
AUDIO_INDEX=1
SUB_SI=1
START_EP="S02E16"

Пояснения:
- VIDEO_DIR: корневая папка с сезонами/эпизодами.
- AUDIO_INDEX=1: вторая аудиодорожка (0-based среди аудио).
- SUB_SI=1: второй поток субтитров (0-based среди subtitle streams).
- START_EP: начать с указанного эпизода (ищется по имени SxxEyy). При LOOP=1 плейлист будет циклично начинаться с этого эпизода.

Дополнительно (опционально):
- VIDEO_SIZE="1920x1080"       # если нужно масштабирование
- VIDEO_BITRATE="4500k"
- MAXRATE="6000k"
- BUFSIZE="9000k"
- PRESET="veryfast"
- GOP=48
- FPS="24000/1001"
- AUDIO_BITRATE="160k"
- AUDIO_RATE="48000"
- AUDIO_CHANNELS=2
- SUB_BURN=1                   # 1=прожигать, 0=без субтитров
- SUB_FONTS_DIR="/path/to/fonts"
- SUB_FORCE_STYLE="FontName=DejaVu Sans,FontSize=36"
- LOGLEVEL="info"
- LOOP=1
- PLAYLIST_PATH="var/playlist.txt"
- SUB_PLAYLIST_PATH="/root/downloads/myVideos/vk_stream_subs_playlist.txt"
- FFMPEG_PATH="ffmpeg"

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
- Плейлист строится по файлам *.mkv, сортировка по SxxEyy в названии.
- Субтитры прожигаются через subtitles фильтр (libass).
- Для субтитров создается отдельный плейлист с относительными путями (по умолчанию в VIDEO_DIR), чтобы избежать ошибки "Unsafe file name".
