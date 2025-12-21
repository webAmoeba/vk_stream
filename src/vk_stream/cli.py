#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .common import (
    EP_RE,
    env_bool,
    env_int,
    env_str,
    escape_filter_path,
    load_dotenv,
    parse_exts,
    rotate_start,
    scan_videos,
    write_playlist,
    write_playlist_relative,
)


@dataclass
class Config:
    rtmp_url: str
    stream_key: str
    video_dir: Path
    start_ep: str
    playlist_path: Path
    sub_playlist_path: Path
    loglevel: str
    ffmpeg_path: str
    ffprobe_path: str
    loop: bool
    video_exts: List[str]
    # Audio/subtitle selection
    audio_index: int
    sub_si: int
    # Stream codecs
    video_codec: str
    video_bitrate: str
    maxrate: str
    bufsize: str
    preset: str
    gop: int
    fps: str
    audio_codec: str
    audio_bitrate: str
    audio_rate: str
    audio_channels: int
    # Filters
    sub_burn: bool
    sub_fonts_dir: str
    sub_force_style: str
    draw_text: bool
    title_file: Path
    title_mode: str
    title_prefix: str
    title_delay: int
    title_font_file: str
    title_size: int
    title_color: str
    title_box: bool
    title_box_color: str
    title_box_border: int
    title_x: str
    title_y: str

    @classmethod
    def from_env(cls, cwd: Path) -> "Config":
        rtmp_url = env_str("RTMP_URL", required=True)
        stream_key = env_str("STREAM_KEY", required=True)
        video_dir = env_str("VIDEO_DIR", required=True)
        start_ep = env_str("START_EP", "")

        playlist_path = env_str("PLAYLIST_PATH", str(cwd / "var" / "playlist.txt"))
        playlist_path = Path(playlist_path)
        if not playlist_path.is_absolute():
            playlist_path = cwd / playlist_path

        video_dir_path = Path(video_dir).expanduser()
        if not video_dir_path.is_absolute():
            video_dir_path = cwd / video_dir_path
        video_dir_path = video_dir_path.resolve()

        sub_playlist_path = env_str("SUB_PLAYLIST_PATH", "")
        if sub_playlist_path:
            sub_playlist_path = Path(sub_playlist_path)
            if not sub_playlist_path.is_absolute():
                sub_playlist_path = cwd / sub_playlist_path
        else:
            sub_playlist_path = video_dir_path / "vk_stream_subs_playlist.txt"

        title_file = env_str("STREAM_TITLE_FILE", str(cwd / "var" / "nowplaying.txt"))
        title_file = Path(title_file)
        if not title_file.is_absolute():
            title_file = cwd / title_file

        audio_index = env_int("STREAM_AUDIO_INDEX", default=env_int("AUDIO_INDEX", 0))
        sub_si = env_int("STREAM_SUB_SI", default=env_int("SUB_SI", 0))

        return cls(
            rtmp_url=rtmp_url,
            stream_key=stream_key,
            video_dir=video_dir_path,
            start_ep=start_ep,
            playlist_path=playlist_path,
            sub_playlist_path=sub_playlist_path,
            loglevel=env_str("LOGLEVEL", "info"),
            ffmpeg_path=env_str("FFMPEG_PATH", "ffmpeg"),
            ffprobe_path=env_str("FFPROBE_PATH", "ffprobe"),
            loop=env_bool("LOOP", True),
            video_exts=parse_exts(env_str("VIDEO_EXTS", ".mkv,.mp4,.mov")),
            audio_index=audio_index,
            sub_si=sub_si,
            video_codec=env_str("STREAM_VIDEO_CODEC", "libx264"),
            video_bitrate=env_str("STREAM_VIDEO_BITRATE", "4500k"),
            maxrate=env_str("STREAM_MAXRATE", "6000k"),
            bufsize=env_str("STREAM_BUFSIZE", "9000k"),
            preset=env_str("STREAM_PRESET", "veryfast"),
            gop=env_int("STREAM_GOP", 48),
            fps=env_str("STREAM_FPS", ""),
            audio_codec=env_str("STREAM_AUDIO_CODEC", "aac"),
            audio_bitrate=env_str("STREAM_AUDIO_BITRATE", "160k"),
            audio_rate=env_str("STREAM_AUDIO_RATE", "48000"),
            audio_channels=env_int("STREAM_AUDIO_CHANNELS", 2),
            sub_burn=env_bool("STREAM_SUB_BURN", True),
            sub_fonts_dir=env_str("STREAM_SUB_FONTS_DIR", ""),
            sub_force_style=env_str("STREAM_SUB_FORCE_STYLE", ""),
            draw_text=env_bool("STREAM_DRAW_TEXT", True),
            title_file=title_file,
            title_mode=env_str("STREAM_TITLE_MODE", "stem"),
            title_prefix=env_str("STREAM_TITLE_PREFIX", ""),
            title_delay=env_int("STREAM_TITLE_DELAY", 0),
            title_font_file=env_str(
                "STREAM_TITLE_FONT_FILE",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ),
            title_size=env_int("STREAM_TITLE_SIZE", 36),
            title_color=env_str("STREAM_TITLE_COLOR", "white"),
            title_box=env_bool("STREAM_TITLE_BOX", True),
            title_box_color=env_str("STREAM_TITLE_BOX_COLOR", "black@0.5"),
            title_box_border=env_int("STREAM_TITLE_BOX_BORDER", 10),
            title_x=env_str("STREAM_TITLE_X", "20"),
            title_y=env_str("STREAM_TITLE_Y", "20"),
        )

    def output_url(self) -> str:
        base = self.rtmp_url.rstrip("/")
        return f"{base}/{self.stream_key}"


def title_for_path(path: Path, mode: str) -> str:
    stem = path.stem
    if mode == "episode":
        m = EP_RE.search(stem)
        if m:
            return f"S{m.group('season')}E{m.group('episode')}".upper()
    return stem


def update_title_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text + "\n", encoding="utf-8")
    tmp.replace(path)


def probe_duration_seconds(ffprobe_path: str, input_path: Path) -> float:
    cmd = [
        ffprobe_path,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nw=1:nk=1",
        str(input_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"WARN: ffprobe failed for {input_path}", file=sys.stderr)
        return 0.0
    out = res.stdout.strip()
    try:
        return float(out)
    except ValueError:
        print(f"WARN: ffprobe duration invalid for {input_path}: {out}", file=sys.stderr)
        return 0.0


def title_updater(
    files: List[Path],
    cfg: Config,
    stop_event: threading.Event,
) -> None:
    cache: Dict[Path, float] = {}
    while not stop_event.is_set():
        for f in files:
            if stop_event.is_set():
                return
            duration = cache.get(f)
            if duration is None:
                duration = probe_duration_seconds(cfg.ffprobe_path, f)
                cache[f] = duration
            if duration <= 0:
                duration = 1.0

            title = cfg.title_prefix + title_for_path(f, cfg.title_mode)
            if cfg.title_delay > 0:
                update_title_file(cfg.title_file, "")
                delay = float(cfg.title_delay)
                if delay >= duration:
                    time.sleep(duration)
                else:
                    time.sleep(delay)
                    update_title_file(cfg.title_file, title)
                    remain = duration - delay
                    if remain > 0:
                        time.sleep(remain)
            else:
                update_title_file(cfg.title_file, title)
                time.sleep(duration)

        if not cfg.loop:
            return


def build_vf(cfg: Config) -> Optional[str]:
    filters: List[str] = []

    if cfg.sub_burn:
        subs_path = escape_filter_path(cfg.sub_playlist_path)
        sub = f"subtitles={subs_path}:si={cfg.sub_si}"
        if cfg.sub_fonts_dir:
            fonts = escape_filter_path(Path(cfg.sub_fonts_dir))
            sub += f":fontsdir={fonts}"
        if cfg.sub_force_style:
            sub += f":force_style={cfg.sub_force_style}"
        filters.append(sub)

    if cfg.draw_text:
        textfile = escape_filter_path(cfg.title_file)
        draw = (
            f"drawtext=textfile={textfile}:reload=1"
            f":x={cfg.title_x}:y={cfg.title_y}:fontsize={cfg.title_size}"
            f":fontcolor={cfg.title_color}"
            f":box={'1' if cfg.title_box else '0'}"
            f":boxcolor={cfg.title_box_color}:boxborderw={cfg.title_box_border}"
        )
        if cfg.title_font_file:
            fontfile = escape_filter_path(Path(cfg.title_font_file))
            draw += f":fontfile={fontfile}"
        filters.append(draw)

    if not filters:
        return None
    return ",".join(filters)


def build_ffmpeg_cmd(cfg: Config) -> List[str]:
    if (cfg.sub_burn or cfg.draw_text) and cfg.video_codec == "copy":
        raise ValueError("STREAM_VIDEO_CODEC=copy is not compatible with filters")

    cmd = [
        cfg.ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        cfg.loglevel,
        "-re",
    ]
    if cfg.loop:
        cmd += ["-stream_loop", "-1"]

    cmd += [
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(cfg.playlist_path),
    ]

    vf = build_vf(cfg)
    if vf:
        cmd += ["-vf", vf]

    cmd += [
        "-map",
        "0:v:0",
        "-map",
        f"0:a:{cfg.audio_index}",
    ]

    if cfg.video_codec == "copy":
        cmd += ["-c:v", "copy"]
    else:
        cmd += [
            "-c:v",
            cfg.video_codec,
            "-preset",
            cfg.preset,
            "-pix_fmt",
            "yuv420p",
            "-g",
            str(cfg.gop),
        ]
        if cfg.fps:
            cmd += ["-r", cfg.fps]
        if cfg.video_bitrate:
            cmd += ["-b:v", cfg.video_bitrate]
        if cfg.maxrate:
            cmd += ["-maxrate", cfg.maxrate]
        if cfg.bufsize:
            cmd += ["-bufsize", cfg.bufsize]

    if cfg.audio_codec == "copy":
        cmd += ["-c:a", "copy"]
    else:
        cmd += [
            "-c:a",
            cfg.audio_codec,
            "-b:a",
            cfg.audio_bitrate,
            "-ar",
            cfg.audio_rate,
            "-ac",
            str(cfg.audio_channels),
        ]

    cmd += ["-f", "flv", cfg.output_url()]
    return cmd


def run_ffmpeg(cmd: List[str]) -> int:
    proc = subprocess.Popen(cmd)

    def handle(_sig: int, _frame) -> None:
        try:
            proc.terminate()
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGINT, handle)
    return proc.wait()


def build_playlist_from_env(cfg: Config) -> List[Path]:
    if not cfg.video_dir.exists():
        raise FileNotFoundError(f"VIDEO_DIR does not exist: {cfg.video_dir}")
    files = scan_videos(cfg.video_dir, cfg.video_exts)
    if not files:
        raise FileNotFoundError(
            f"No video files found under: {cfg.video_dir} ({', '.join(cfg.video_exts)})"
        )

    files, idx = rotate_start(files, cfg.start_ep)
    if cfg.start_ep:
        if idx is None:
            print(f"WARN: START_EP not found: {cfg.start_ep}", file=sys.stderr)
        else:
            print(
                f"Start from: {cfg.start_ep} (index {idx + 1}/{len(files)})",
                file=sys.stderr,
            )

    write_playlist(files, cfg.playlist_path)
    print(f"Playlist: {cfg.playlist_path} ({len(files)} files)", file=sys.stderr)

    if cfg.sub_burn:
        write_playlist_relative(files, cfg.sub_playlist_path, cfg.video_dir)
        print(
            f"Sub playlist: {cfg.sub_playlist_path} ({len(files)} files)",
            file=sys.stderr,
        )

    return files


def main(argv: Optional[List[str]] = None) -> int:
    cwd = Path.cwd()
    load_dotenv(cwd / ".env")

    parser = argparse.ArgumentParser(description="VK 24/7 video streamer")
    parser.add_argument("--dry-run", action="store_true", help="Print ffmpeg command and exit")
    parser.add_argument(
        "--gen-playlist", action="store_true", help="Only generate playlist and exit"
    )
    args = parser.parse_args(argv)

    try:
        config = Config.from_env(cwd)
    except Exception as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    try:
        files = build_playlist_from_env(config)
    except Exception as exc:
        print(f"Playlist error: {exc}", file=sys.stderr)
        return 2

    if args.gen_playlist:
        return 0

    stop_event = threading.Event()
    if config.draw_text:
        update_title_file(config.title_file, "")
        t = threading.Thread(
            target=title_updater,
            args=(files, config, stop_event),
            daemon=True,
        )
        t.start()

    cmd = build_ffmpeg_cmd(config)
    print("FFmpeg:", shlex.join(cmd), file=sys.stderr)
    if args.dry_run:
        return 0
    try:
        return run_ffmpeg(cmd)
    finally:
        stop_event.set()


if __name__ == "__main__":
    raise SystemExit(main())
