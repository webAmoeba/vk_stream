#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shlex
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


EP_RE = re.compile(r"S(?P<season>\d{2})E(?P<episode>\d{2})", re.IGNORECASE)


def load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    for raw in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if not key:
            continue
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        os.environ.setdefault(key, val)


def env_str(key: str, default: Optional[str] = None, required: bool = False) -> str:
    val = os.environ.get(key, default)
    if required and (val is None or val == ""):
        raise ValueError(f"Missing required env: {key}")
    return "" if val is None else str(val)


def env_int(key: str, default: Optional[int] = None, required: bool = False) -> int:
    val = os.environ.get(key)
    if val is None or val == "":
        if required:
            raise ValueError(f"Missing required env: {key}")
        if default is None:
            return 0
        return int(default)
    try:
        return int(val)
    except ValueError as exc:
        raise ValueError(f"Invalid int for {key}: {val}") from exc


def env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_size(value: str) -> Tuple[int, int]:
    if "x" not in value:
        raise ValueError(f"Invalid VIDEO_SIZE format: {value}")
    w_s, h_s = value.lower().split("x", 1)
    return int(w_s), int(h_s)


def ffconcat_quote(path: Path) -> str:
    s = str(path)
    # concat demuxer understands single-quoted strings; double quotes are not stripped
    if "'" not in s:
        return f"'{s}'"
    # Fallback: escape spaces and backslashes
    s = s.replace("\\", "\\\\").replace(" ", "\\ ").replace("#", "\\#")
    return s


def escape_filter_path(path: Path) -> str:
    s = str(path)
    s = s.replace("\\", "\\\\")
    s = s.replace(":", "\\:")
    s = s.replace(" ", "\\ ")
    return s


def sort_key(path: Path) -> Tuple[int, int, int, str]:
    m = EP_RE.search(path.name)
    if m:
        return (0, int(m.group("season")), int(m.group("episode")), path.name.lower())
    return (1, 0, 0, path.name.lower())


def scan_videos(video_dir: Path) -> List[Path]:
    files: List[Path] = []
    for p in video_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() == ".mkv":
            files.append(p)
    return sorted(files, key=sort_key)


def rotate_start(files: List[Path], start_ep: str) -> Tuple[List[Path], Optional[int]]:
    if not start_ep:
        return files, None
    needle = start_ep.strip().upper()
    for i, p in enumerate(files):
        stem = p.stem.upper()
        if stem == needle or needle in stem:
            return files[i:] + files[:i], i
    return files, None


def write_playlist(files: Iterable[Path], playlist_path: Path) -> None:
    playlist_path.parent.mkdir(parents=True, exist_ok=True)
    with playlist_path.open("w", encoding="utf-8") as f:
        f.write("ffconcat version 1.0\n")
        for p in files:
            f.write(f"file {ffconcat_quote(p)}\n")


@dataclass
class Config:
    rtmp_url: str
    stream_key: str
    video_dir: Path
    audio_index: int
    sub_si: int
    start_ep: str
    playlist_path: Path
    video_size: str
    video_bitrate: str
    maxrate: str
    bufsize: str
    preset: str
    gop: int
    fps: str
    audio_bitrate: str
    audio_rate: str
    audio_channels: int
    loglevel: str
    ffmpeg_path: str
    sub_burn: bool
    sub_fonts_dir: str
    sub_force_style: str
    loop: bool

    @classmethod
    def from_env(cls, cwd: Path) -> "Config":
        rtmp_url = env_str("RTMP_URL", required=True)
        stream_key = env_str("STREAM_KEY", required=True)
        video_dir = env_str("VIDEO_DIR", required=True)
        audio_index = env_int("AUDIO_INDEX", required=True)
        sub_burn = env_bool("SUB_BURN", True)
        sub_si = env_int("SUB_SI", required=sub_burn)
        start_ep = env_str("START_EP", "")

        playlist_path = env_str("PLAYLIST_PATH", str(cwd / "var" / "playlist.txt"))
        playlist_path = Path(playlist_path)
        if not playlist_path.is_absolute():
            playlist_path = cwd / playlist_path

        video_dir_path = Path(video_dir).expanduser()
        if not video_dir_path.is_absolute():
            video_dir_path = cwd / video_dir_path
        video_dir_path = video_dir_path.resolve()

        return cls(
            rtmp_url=rtmp_url,
            stream_key=stream_key,
            video_dir=video_dir_path,
            audio_index=audio_index,
            sub_si=sub_si,
            start_ep=start_ep,
            playlist_path=playlist_path,
            video_size=env_str("VIDEO_SIZE", ""),
            video_bitrate=env_str("VIDEO_BITRATE", "4500k"),
            maxrate=env_str("MAXRATE", "6000k"),
            bufsize=env_str("BUFSIZE", "9000k"),
            preset=env_str("PRESET", "veryfast"),
            gop=env_int("GOP", 48),
            fps=env_str("FPS", ""),
            audio_bitrate=env_str("AUDIO_BITRATE", "160k"),
            audio_rate=env_str("AUDIO_RATE", "48000"),
            audio_channels=env_int("AUDIO_CHANNELS", 2),
            loglevel=env_str("LOGLEVEL", "info"),
            ffmpeg_path=env_str("FFMPEG_PATH", "ffmpeg"),
            sub_burn=sub_burn,
            sub_fonts_dir=env_str("SUB_FONTS_DIR", ""),
            sub_force_style=env_str("SUB_FORCE_STYLE", ""),
            loop=env_bool("LOOP", True),
        )

    def output_url(self) -> str:
        base = self.rtmp_url.rstrip("/")
        return f"{base}/{self.stream_key}"


def build_vf(config: Config) -> Optional[str]:
    filters: List[str] = []

    if config.video_size:
        w, h = parse_size(config.video_size)
        filters.append(f"scale={w}:{h}")

    if config.sub_burn:
        subs_path = escape_filter_path(config.playlist_path)
        sub = f"subtitles={subs_path}:f=concat:si={config.sub_si}"
        if config.sub_fonts_dir:
            fonts = escape_filter_path(Path(config.sub_fonts_dir))
            sub += f":fontsdir={fonts}"
        if config.sub_force_style:
            sub += f":force_style={config.sub_force_style}"
        filters.append(sub)

    if not filters:
        return None
    return ",".join(filters)


def build_ffmpeg_cmd(config: Config) -> List[str]:
    cmd = [
        config.ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        config.loglevel,
        "-re",
    ]
    if config.loop:
        cmd += ["-stream_loop", "-1"]

    cmd += [
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(config.playlist_path),
    ]

    vf = build_vf(config)
    if vf:
        cmd += ["-vf", vf]

    cmd += [
        "-map",
        "0:v:0",
        "-map",
        f"0:a:{config.audio_index}",
        "-c:v",
        "libx264",
        "-preset",
        config.preset,
        "-pix_fmt",
        "yuv420p",
        "-g",
        str(config.gop),
    ]

    if config.fps:
        cmd += ["-r", config.fps]
    if config.video_bitrate:
        cmd += ["-b:v", config.video_bitrate]
    if config.maxrate:
        cmd += ["-maxrate", config.maxrate]
    if config.bufsize:
        cmd += ["-bufsize", config.bufsize]

    cmd += [
        "-c:a",
        "aac",
        "-b:a",
        config.audio_bitrate,
        "-ar",
        config.audio_rate,
        "-ac",
        str(config.audio_channels),
        "-f",
        "flv",
        config.output_url(),
    ]
    return cmd


def run_ffmpeg(cmd: List[str]) -> int:
    proc = subprocess.Popen(cmd)

    def handle(sig: int, _frame) -> None:
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


def build_playlist(config: Config) -> None:
    if not config.video_dir.exists():
        raise FileNotFoundError(f"VIDEO_DIR does not exist: {config.video_dir}")
    files = scan_videos(config.video_dir)
    if not files:
        raise FileNotFoundError(f"No .mkv files found under: {config.video_dir}")

    files, idx = rotate_start(files, config.start_ep)
    if config.start_ep:
        if idx is None:
            print(f"WARN: START_EP not found: {config.start_ep}", file=sys.stderr)
        else:
            print(
                f"Start from: {config.start_ep} (index {idx + 1}/{len(files)})",
                file=sys.stderr,
            )

    write_playlist(files, config.playlist_path)
    print(f"Playlist: {config.playlist_path} ({len(files)} files)", file=sys.stderr)


def main(argv: Optional[List[str]] = None) -> int:
    cwd = Path.cwd()
    load_dotenv(cwd / ".env")

    parser = argparse.ArgumentParser(description="VK 24/7 MKV streamer")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print ffmpeg command and exit",
    )
    parser.add_argument(
        "--gen-playlist",
        action="store_true",
        help="Only generate playlist and exit",
    )
    args = parser.parse_args(argv)

    try:
        config = Config.from_env(cwd)
    except Exception as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    try:
        build_playlist(config)
    except Exception as exc:
        print(f"Playlist error: {exc}", file=sys.stderr)
        return 2

    if args.gen_playlist:
        return 0

    cmd = build_ffmpeg_cmd(config)
    print("FFmpeg:", shlex.join(cmd), file=sys.stderr)
    if args.dry_run:
        return 0
    return run_ffmpeg(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
