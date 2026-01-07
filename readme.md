vk_stream — минимальный зацикленный стример MP4 в VK Live/Video (RTMP)

Что делает
- Берёт файлы `.mp4` из папки `videos` (без подпапок), сортирует по имени и крутит по кругу.
- По умолчанию перекодирует в H.264/AAC с низким битрейтом (200k/32k) — подходит для маломощных серверов.
- Можно включить пасстру без перекодирования через `FFMPEG_COPY=1`.
- Никаких субтитров, выбора дорожек и лишних опций.

Требования
- Ubuntu 24.04
- ffmpeg
- make
- Python 3.10+

Установка
```
make install
```
Команда поставит ffmpeg (если его нет), установит uv, создаст `.venv` и установит пакет в режиме `-e`.

Настройка
```
cp .env.example .env
```
Минимум: заполните `VK_STREAM_URL` (или `VK_URL` + `VK_KEY`). По умолчанию берётся папка `videos` в корне проекта.

Запуск
```
make start      # запустить/перезапустить сервис
make status     # статус systemd
make logs       # последние логи
```
Проверка без стрима:
```
VK_STREAM_URL="rtmp://<vk-server>/input/<vk-key>" python -m vk_stream --dry-run
```

Основные переменные окружения
- `VK_STREAM_URL` — полный RTMP (обязательно), альтернатива: `VK_URL` + `VK_KEY`.
- `VIDEO_DIR` — папка с mp4, по умолчанию `videos`.
- `FFMPEG_COPY` — `1` чтобы не перекодировать (минимальная нагрузка).
- `VIDEO_BITRATE` (200k), `BUF_SIZE` (400k), `PRESET` (veryfast), `GOP` (50).
- `AUDIO_BITRATE` (32k), `AUDIO_RATE` (22050), `AUDIO_CHANNELS` (1).
- `LOGLEVEL` (info), `FFMPEG_PATH` (ffmpeg).
