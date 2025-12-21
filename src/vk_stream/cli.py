#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .common import EP_RE, env_bool, env_int, env_str, escape_filter_path, load_dotenv, parse_exts, scan_videos

PAUSE_SECONDS = 30


@dataclass
class Config:
    rtmp_url: str
    stream_key: str
    video_dir: Path
    start_ep: str
    loop: bool
    loglevel: str
    ffmpeg_path: str
    video_exts: List[str]
    audio_index: int
    sub_si: int
    video_bitrate: str
    maxrate: str
    bufsize: str
    preset: str
    gop: int
    audio_bitrate: str
    audio_rate: str
    audio_channels: int

    @classmethod
    def from_env(cls, cwd: Path) -> "Config":
        rtmp_url = env_str("RTMP_URL", required=True)
        stream_key = env_str("STREAM_KEY", required=True)
        video_dir = env_str("VIDEO_DIR", required=True)
        start_ep = env_str("START_EP", "")

        video_dir_path = Path(video_dir).expanduser()
        if not video_dir_path.is_absolute():
            video_dir_path = cwd / video_dir_path
        video_dir_path = video_dir_path.resolve()

        return cls(
            rtmp_url=rtmp_url,
            stream_key=stream_key,
            video_dir=video_dir_path,
            start_ep=start_ep,
            loop=env_bool("LOOP", True),
            loglevel=env_str("LOGLEVEL", "info"),
            ffmpeg_path=env_str("FFMPEG_PATH", "ffmpeg"),
            video_exts=parse_exts(env_str("VIDEO_EXTS", ".mkv")),
            audio_index=env_int("AUDIO_INDEX", default=1),
            sub_si=env_int("SUB_SI", default=1),
            video_bitrate=env_str("STREAM_VIDEO_BITRATE", "4500k"),
            maxrate=env_str("STREAM_MAXRATE", "6000k"),
            bufsize=env_str("STREAM_BUFSIZE", "9000k"),
            preset=env_str("STREAM_PRESET", "veryfast"),
            gop=env_int("STREAM_GOP", default=48),
            audio_bitrate=env_str("STREAM_AUDIO_BITRATE", "160k"),
            audio_rate=env_str("STREAM_AUDIO_RATE", "48000"),
            audio_channels=env_int("STREAM_AUDIO_CHANNELS", default=2),
        )

    def output_url(self) -> str:
        base = self.rtmp_url.rstrip("/")
        return f"{base}/{self.stream_key}"


def find_start_index(files: List[Path], start_ep: str) -> Optional[int]:
    if not start_ep:
        return None
    needle = start_ep.strip().upper()
    for i, p in enumerate(files):
        stem = p.stem.upper()
        if stem == needle or needle in stem:
            return i
    return None


def title_for_path(path: Path) -> str:
    m = EP_RE.search(path.stem)
    if m:
        return f"S{m.group('season')}E{m.group('episode')}".upper()
    raw = path.stem
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in raw)
    return safe[:64] if safe else "VIDEO"


def build_ffmpeg_cmd(cfg: Config, input_path: Path) -> List[str]:
    subs_path = escape_filter_path(input_path)
    title = title_for_path(input_path)
    vf = (
        f"subtitles={subs_path}:si={cfg.sub_si},"
        f"drawtext=text='{title}':x=20:y=20:fontsize=36:fontcolor=white:"
        f"box=1:boxcolor=black@0.5:boxborderw=10"
    )

    cmd = [
        cfg.ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        cfg.loglevel,
        "-re",
        "-i",
        str(input_path),
    ]

    cmd += [
        "-vf",
        vf,
        "-map",
        "0:v:0",
        "-map",
        f"0:a:{cfg.audio_index}",
        "-c:v",
        "libx264",
        "-preset",
        cfg.preset,
        "-pix_fmt",
        "yuv420p",
        "-g",
        str(cfg.gop),
        "-b:v",
        cfg.video_bitrate,
        "-maxrate",
        cfg.maxrate,
        "-bufsize",
        cfg.bufsize,
        "-c:a",
        "aac",
        "-b:a",
        cfg.audio_bitrate,
        "-ar",
        cfg.audio_rate,
        "-ac",
        str(cfg.audio_channels),
        "-f",
        "flv",
        cfg.output_url(),
    ]
    return cmd


def stream_files(cfg: Config, files: List[Path], dry_run: bool) -> int:
    if not files:
        print("No video files found.", file=sys.stderr)
        return 2

    start_idx = find_start_index(files, cfg.start_ep)
    if cfg.start_ep and start_idx is None:
        print(f"WARN: START_EP not found: {cfg.start_ep}", file=sys.stderr)
        start_idx = 0

    current_proc: Optional[subprocess.Popen] = None
    stop = False

    def handle(_sig: int, _frame) -> None:
        nonlocal stop
        stop = True
        if current_proc and current_proc.poll() is None:
            try:
                current_proc.terminate()
            except ProcessLookupError:
                return
            try:
                current_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                current_proc.kill()

    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGINT, handle)

    first_pass = True
    while True:
        if first_pass and start_idx:
            order = files[start_idx:] + files[:start_idx]
        else:
            order = files

        for idx, f in enumerate(order, start=1):
            if stop:
                return 0
            if PAUSE_SECONDS and not (first_pass and idx == 1):
                print(f"Pause {PAUSE_SECONDS}s before next file...", file=sys.stderr)
                time.sleep(PAUSE_SECONDS)
            print(
                f"Playing {idx}/{len(order)}: {f}",
                file=sys.stderr,
            )
            cmd = build_ffmpeg_cmd(cfg, f)
            print("FFmpeg:", shlex.join(cmd), file=sys.stderr)
            if dry_run:
                return 0

            current_proc = subprocess.Popen(cmd)
            code = current_proc.wait()
            if stop:
                return code
            if code != 0:
                return code

        if not cfg.loop:
            break
        first_pass = False

    return 0


def main(argv: Optional[List[str]] = None) -> int:
    cwd = Path.cwd()
    load_dotenv(cwd / ".env")

    parser = argparse.ArgumentParser(description="VK video streamer (simple, per-file)")
    parser.add_argument("--dry-run", action="store_true", help="Print ffmpeg command and exit")
    args = parser.parse_args(argv)

    try:
        cfg = Config.from_env(cwd)
    except Exception as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    if not cfg.video_dir.exists():
        print(f"VIDEO_DIR does not exist: {cfg.video_dir}", file=sys.stderr)
        return 2

    files = scan_videos(cfg.video_dir, cfg.video_exts)
    return stream_files(cfg, files, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
