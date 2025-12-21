#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .common import (
    env_bool,
    env_int,
    env_str,
    load_dotenv,
    parse_exts,
    rotate_start,
    scan_videos,
    write_playlist,
)


@dataclass
class Config:
    rtmp_url: str
    stream_key: str
    video_dir: Path
    start_ep: str
    playlist_path: Path
    loglevel: str
    ffmpeg_path: str
    loop: bool
    video_exts: List[str]
    video_codec: str
    audio_codec: str
    audio_bitrate: str
    audio_rate: str
    audio_channels: int

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

        return cls(
            rtmp_url=rtmp_url,
            stream_key=stream_key,
            video_dir=video_dir_path,
            start_ep=start_ep,
            playlist_path=playlist_path,
            loglevel=env_str("LOGLEVEL", "info"),
            ffmpeg_path=env_str("FFMPEG_PATH", "ffmpeg"),
            loop=env_bool("LOOP", True),
            video_exts=parse_exts(env_str("VIDEO_EXTS", ".mp4,.mkv,.mov")),
            video_codec=env_str("STREAM_VIDEO_CODEC", "copy"),
            audio_codec=env_str("STREAM_AUDIO_CODEC", "aac"),
            audio_bitrate=env_str("STREAM_AUDIO_BITRATE", "160k"),
            audio_rate=env_str("STREAM_AUDIO_RATE", "48000"),
            audio_channels=env_int("STREAM_AUDIO_CHANNELS", 2),
        )

    def output_url(self) -> str:
        base = self.rtmp_url.rstrip("/")
        return f"{base}/{self.stream_key}"


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
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
    ]

    cmd += ["-c:v", config.video_codec]

    if config.audio_codec == "copy":
        cmd += ["-c:a", "copy"]
    else:
        cmd += [
            "-c:a",
            config.audio_codec,
            "-b:a",
            config.audio_bitrate,
            "-ar",
            config.audio_rate,
            "-ac",
            str(config.audio_channels),
        ]

    cmd += ["-f", "flv", config.output_url()]
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


def build_playlist_from_env(config: Config) -> None:
    if not config.video_dir.exists():
        raise FileNotFoundError(f"VIDEO_DIR does not exist: {config.video_dir}")
    files = scan_videos(config.video_dir, config.video_exts)
    if not files:
        raise FileNotFoundError(
            f"No video files found under: {config.video_dir} ({', '.join(config.video_exts)})"
        )

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
        build_playlist_from_env(config)
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
