from __future__ import annotations

import os
import re
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


def ffconcat_quote(path: Path) -> str:
    s = str(path)
    if "'" not in s:
        return f"'{s}'"
    s = s.replace("\\", "\\\\").replace(" ", "\\ ").replace("#", "\\#")
    return s


def escape_filter_path(path: Path) -> str:
    s = str(path)
    s = s.replace("\\", "\\\\")
    s = s.replace(":", "\\:")
    s = s.replace(" ", "\\ ")
    return s


def parse_exts(raw: str, default: Optional[List[str]] = None) -> List[str]:
    parts = [p.strip().lower() for p in raw.replace(" ", ",").split(",") if p.strip()]
    exts: List[str] = []
    for p in parts:
        if not p.startswith("."):
            p = "." + p
        exts.append(p)
    return exts or (default or [".mp4", ".mkv", ".mov"])


def sort_key(path: Path) -> Tuple[int, int, int, str]:
    m = EP_RE.search(path.stem)
    if m:
        return (
            0,
            int(m.group("season")),
            int(m.group("episode")),
            path.as_posix().lower(),
        )
    return (1, 0, 0, path.as_posix().lower())


def scan_videos(video_dir: Path, exts: Iterable[str]) -> List[Path]:
    exts_lc = {e.lower() for e in exts}
    files: List[Path] = []
    for p in video_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts_lc:
            files.append(p)

    # Prefer mp4 over mkv if both exist for same path without extension
    priority = {".mp4": 0, ".mkv": 1, ".mov": 2}
    chosen: dict[Path, Path] = {}
    for p in files:
        key = p.with_suffix("")
        existing = chosen.get(key)
        if existing is None:
            chosen[key] = p
            continue
        if priority.get(p.suffix.lower(), 99) < priority.get(
            existing.suffix.lower(), 99
        ):
            chosen[key] = p

    return sorted(chosen.values(), key=sort_key)


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
