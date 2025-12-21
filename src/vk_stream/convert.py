#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .common import (
    env_bool,
    env_int,
    env_str,
    escape_filter_path,
    load_dotenv,
    parse_exts,
    scan_videos,
    sort_key,
)


def parse_size(value: str) -> Optional[tuple[int, int]]:
    if not value:
        return None
    if "x" not in value:
        raise ValueError(f"Invalid CONVERT_SCALE format: {value}")
    w_s, h_s = value.lower().split("x", 1)
    return int(w_s), int(h_s)


@dataclass
class ConvertConfig:
    video_dir: Path
    audio_index: int
    sub_si: int
    sub_burn: bool
    preset: str
    crf: int
    vbitrate: str
    maxrate: str
    bufsize: str
    audio_bitrate: str
    audio_rate: str
    audio_channels: int
    loglevel: str
    ffmpeg_path: str
    out_ext: str
    scale: Optional[tuple[int, int]]
    input_exts: List[str]
    overwrite: bool

    @classmethod
    def from_env(cls, cwd: Path) -> "ConvertConfig":
        video_dir = env_str("VIDEO_DIR", required=True)
        audio_index = env_int(
            "CONVERT_AUDIO_INDEX",
            default=env_int("AUDIO_INDEX", default=0),
        )
        sub_si = env_int(
            "CONVERT_SUB_SI",
            default=env_int("SUB_SI", default=0),
        )
        sub_burn = env_bool("CONVERT_SUB_BURN", True)
        preset = env_str("CONVERT_PRESET", "veryfast")
        crf = env_int("CONVERT_CRF", 20)
        vbitrate = env_str("CONVERT_VBITRATE", "")
        maxrate = env_str("CONVERT_MAXRATE", "")
        bufsize = env_str("CONVERT_BUFSIZE", "")
        audio_bitrate = env_str("CONVERT_AUDIO_BITRATE", "160k")
        audio_rate = env_str("CONVERT_AUDIO_RATE", "48000")
        audio_channels = env_int("CONVERT_AUDIO_CHANNELS", 2)
        loglevel = env_str("CONVERT_LOGLEVEL", "info")
        ffmpeg_path = env_str("FFMPEG_PATH", "ffmpeg")
        out_ext = env_str("CONVERT_OUT_EXT", ".mp4")
        if not out_ext.startswith("."):
            out_ext = "." + out_ext
        scale = parse_size(env_str("CONVERT_SCALE", ""))
        input_exts = parse_exts(env_str("CONVERT_INPUT_EXTS", ".mkv"), default=[".mkv"])
        overwrite = env_bool("CONVERT_OVERWRITE", False)

        video_dir_path = Path(video_dir).expanduser()
        if not video_dir_path.is_absolute():
            video_dir_path = cwd / video_dir_path
        video_dir_path = video_dir_path.resolve()

        return cls(
            video_dir=video_dir_path,
            audio_index=audio_index,
            sub_si=sub_si,
            sub_burn=sub_burn,
            preset=preset,
            crf=crf,
            vbitrate=vbitrate,
            maxrate=maxrate,
            bufsize=bufsize,
            audio_bitrate=audio_bitrate,
            audio_rate=audio_rate,
            audio_channels=audio_channels,
            loglevel=loglevel,
            ffmpeg_path=ffmpeg_path,
            out_ext=out_ext,
            scale=scale,
            input_exts=input_exts,
            overwrite=overwrite,
        )


def build_vf(cfg: ConvertConfig, input_path: Path) -> Optional[str]:
    filters: List[str] = []
    if cfg.sub_burn:
        subs = escape_filter_path(input_path)
        filters.append(f"subtitles={subs}:si={cfg.sub_si}")
    if cfg.scale:
        w, h = cfg.scale
        filters.append(f"scale={w}:{h}")
    if not filters:
        return None
    return ",".join(filters)


def output_paths(input_path: Path, out_ext: str) -> tuple[Path, Path]:
    out = input_path.with_suffix(out_ext)
    tmp = out.with_suffix(out.suffix + ".tmp")
    return out, tmp


def run_ffmpeg(cmd: List[str]) -> int:
    proc = subprocess.run(cmd)
    return proc.returncode


def convert_one(
    cfg: ConvertConfig,
    input_path: Path,
    delete_original: bool,
    dry_run: bool,
) -> tuple[int, str, bool]:
    """
    Returns: (rc, status, deleted_original)
    status in {"converted", "skipped", "dry-run", "failed"}.
    """
    if not input_path.exists():
        print(f"Missing input: {input_path}", file=sys.stderr)
        return 2, "failed", False

    out_path, tmp_path = output_paths(input_path, cfg.out_ext)
    if out_path.exists() and not cfg.overwrite:
        if delete_original and out_path.stat().st_size > 1024 * 1024:
            input_path.unlink(missing_ok=True)
            print(f"Deleted original (output exists): {input_path}", file=sys.stderr)
            return 0, "skipped", True
        print(f"Skip (output exists): {out_path}", file=sys.stderr)
        return 0, "skipped", False

    print(f"Converting: {input_path}", file=sys.stderr)

    vf = build_vf(cfg, input_path)
    cmd = [
        cfg.ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        cfg.loglevel,
    ]
    if cfg.overwrite:
        cmd += ["-y"]
    cmd += [
        "-i",
        str(input_path),
        "-map",
        "0:v:0",
        "-map",
        f"0:a:{cfg.audio_index}",
    ]
    if vf:
        cmd += ["-vf", vf]

    cmd += [
        "-c:v",
        "libx264",
        "-preset",
        cfg.preset,
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        cfg.audio_bitrate,
        "-ar",
        cfg.audio_rate,
        "-ac",
        str(cfg.audio_channels),
        "-f",
        "mp4",
        str(tmp_path),
    ]

    if cfg.vbitrate:
        cmd += ["-b:v", cfg.vbitrate]
        if cfg.maxrate:
            cmd += ["-maxrate", cfg.maxrate]
        if cfg.bufsize:
            cmd += ["-bufsize", cfg.bufsize]
    else:
        cmd += ["-crf", str(cfg.crf)]

    print("FFmpeg:", shlex.join(cmd), file=sys.stderr)
    if dry_run:
        return 0, "dry-run", False

    if tmp_path.exists():
        tmp_path.unlink()
    rc = run_ffmpeg(cmd)
    if rc != 0:
        if tmp_path.exists():
            tmp_path.unlink()
        return rc, "failed", False

    if out_path.exists():
        out_path.unlink()
    tmp_path.rename(out_path)

    if delete_original:
        if out_path.exists() and out_path.stat().st_size > 0:
            input_path.unlink(missing_ok=True)
            print(f"Deleted original: {input_path}", file=sys.stderr)
            return 0, "converted", True
    return 0, "converted", False


def main(argv: Optional[List[str]] = None) -> int:
    cwd = Path.cwd()
    load_dotenv(cwd / ".env")

    parser = argparse.ArgumentParser(description="Convert videos with burned subtitles")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--one", metavar="FILE", help="Convert a single file")
    group.add_argument("--all", action="store_true", help="Convert all files under VIDEO_DIR")
    parser.add_argument(
        "--delete-original",
        action="store_true",
        help="Delete source file after successful conversion",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print commands only")
    args = parser.parse_args(argv)

    try:
        cfg = ConvertConfig.from_env(cwd)
    except Exception as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    if not cfg.video_dir.exists():
        print(f"VIDEO_DIR does not exist: {cfg.video_dir}", file=sys.stderr)
        return 2

    if args.one:
        rc, _status, _deleted = convert_one(
            cfg, Path(args.one), args.delete_original, args.dry_run
        )
        if rc == 0 and not args.dry_run:
            print("Done.", file=sys.stderr)
        return rc

    # --all
    files = scan_videos(cfg.video_dir, cfg.input_exts)
    if not files:
        print("No input files found", file=sys.stderr)
        return 2

    # Ensure deterministic order even if ext priority removed duplicates
    files = sorted(files, key=sort_key)

    total = len(files)
    converted = skipped = deleted = dry_run = 0

    print(f"Starting convert-all: {total} file(s)", file=sys.stderr)
    for f in files:
        rc, status, was_deleted = convert_one(cfg, f, args.delete_original, args.dry_run)
        if status == "converted":
            converted += 1
        elif status == "skipped":
            skipped += 1
        elif status == "dry-run":
            dry_run += 1
        if was_deleted:
            deleted += 1
        if rc != 0:
            print("Stopped due to error.", file=sys.stderr)
            return rc

    print(
        f"Done. converted={converted} skipped={skipped} deleted={deleted} dry-run={dry_run}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
