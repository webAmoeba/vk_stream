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

from .common import env_bool, env_int, env_str, load_dotenv, resolve_dir, scan_videos


@dataclass
class Config:
    stream_url: str
    video_dir: Path
    loglevel: str
    ffmpeg_path: str
    copy_mode: bool
    video_bitrate: str
    bufsize: str
    preset: str
    gop: int
    audio_bitrate: str
    audio_rate: int
    audio_channels: int

    @classmethod
    def from_env(cls, cwd: Path) -> "Config":
        load_dotenv(cwd / ".env")

        stream_url = env_str("VK_STREAM_URL", "").strip()
        if not stream_url:
            vk_url = env_str("VK_URL", "").strip()
            vk_key = env_str("VK_KEY", "").strip()
            if vk_url and vk_key:
                stream_url = f"{vk_url.rstrip('/')}/{vk_key}"

        if not stream_url:
            raise ValueError("Provide VK_STREAM_URL or VK_URL + VK_KEY")

        video_dir_path = resolve_dir(env_str("VIDEO_DIR", "videos"), cwd)
        if not video_dir_path.exists():
            raise ValueError(f"VIDEO_DIR does not exist: {video_dir_path}")
        if not video_dir_path.is_dir():
            raise ValueError(f"VIDEO_DIR is not a directory: {video_dir_path}")

        return cls(
            stream_url=stream_url,
            video_dir=video_dir_path,
            loglevel=env_str("LOGLEVEL", "info"),
            ffmpeg_path=env_str("FFMPEG_PATH", "ffmpeg"),
            copy_mode=env_bool("FFMPEG_COPY", False),
            video_bitrate=env_str("VIDEO_BITRATE", "200k"),
            bufsize=env_str("BUF_SIZE", "400k"),
            preset=env_str("PRESET", "veryfast"),
            gop=env_int("GOP", default=50),
            audio_bitrate=env_str("AUDIO_BITRATE", "32k"),
            audio_rate=env_int("AUDIO_RATE", default=22050),
            audio_channels=env_int("AUDIO_CHANNELS", default=1),
        )

    def ffmpeg_cmd(self, input_path: Path) -> List[str]:
        cmd: List[str] = [
            self.ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            self.loglevel,
            "-re",
            "-i",
            str(input_path),
        ]
        if self.copy_mode:
            cmd += [
                "-c",
                "copy",
                "-f",
                "flv",
                self.stream_url,
            ]
        else:
            cmd += [
                "-c:v",
                "libx264",
                "-preset",
                self.preset,
                "-pix_fmt",
                "yuv420p",
                "-b:v",
                self.video_bitrate,
                "-maxrate",
                self.video_bitrate,
                "-bufsize",
                self.bufsize,
                "-g",
                str(self.gop),
                "-c:a",
                "aac",
                "-b:a",
                self.audio_bitrate,
                "-ar",
                str(self.audio_rate),
                "-ac",
                str(self.audio_channels),
                "-f",
                "flv",
                self.stream_url,
            ]
        return cmd


def stream(cfg: Config, dry_run: bool) -> int:
    files = scan_videos(cfg.video_dir)
    if not files:
        print(f"No .mp4 files in {cfg.video_dir}", file=sys.stderr)
        return 2

    if dry_run:
        for idx, f in enumerate(files, start=1):
            cmd = cfg.ffmpeg_cmd(f)
            print(f"[{idx}/{len(files)}] {f.name}")
            print("    " + shlex.join(cmd))
        return 0

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

    while True:
        files = scan_videos(cfg.video_dir)
        if not files:
            print(f"No .mp4 files in {cfg.video_dir}", file=sys.stderr)
            return 2

        for idx, f in enumerate(files, start=1):
            if stop:
                return 0
            print(f"Playing {idx}/{len(files)}: {f.name}", file=sys.stderr)
            cmd = cfg.ffmpeg_cmd(f)
            print("FFmpeg:", shlex.join(cmd), file=sys.stderr)
            current_proc = subprocess.Popen(cmd)
            code = current_proc.wait()
            if stop:
                return 0
            if code != 0:
                print(f"ffmpeg exited with code {code} on {f.name}", file=sys.stderr)
                return code
        # restart from first file automatically

    return 0


def main(argv: Optional[List[str]] = None) -> int:
    cwd = Path.cwd()

    parser = argparse.ArgumentParser(description="VK video streamer (simple mp4 loop)")
    parser.add_argument("--dry-run", action="store_true", help="Print ffmpeg command and exit")
    args = parser.parse_args(argv)

    try:
        cfg = Config.from_env(cwd)
    except Exception as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    return stream(cfg, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
