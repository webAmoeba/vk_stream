vk_stream — простой стример MKV в VK Live (RTMP)

Проект стримит файлы по одному, с прожигом субтитров.
Между файлами есть пауза 30 секунд — это нормально.

1) Требования
- Ubuntu 24.04
- ffmpeg
- make
- uv (ставится через make install)

2) Установка
Из корня проекта:
make install

3) Настройка .env
Скопируйте пример:
cp .env.example .env

Минимум:
RTMP_URL="rtmp://<vk-server>/input/"
STREAM_KEY="<vk-key>"
VIDEO_DIR="/root/downloads/myVideos"
START_EP="S02E16"

Опционально:
- VIDEO_EXTS=".mkv"
- LOOP=1
- AUDIO_INDEX=1
- SUB_SI=1

4) Запуск
make start
make status
make logs

5) Заметки
- START_EP влияет только на первый запуск цикла.
  Когда дойдёт до последнего файла, новый круг начнётся с первого.
- Если START_EP не найден, начнётся с первого файла.
- Название файла выводится в левом верхнем углу (формат S01E01).
