from __future__ import annotations

import os
from pathlib import Path
from typing import List


def load_dotenv(dotenv_path: Path) -> None:
    """Minimal .env loader (KEY=VALUE, optional quotes, ignores comments)."""
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
        if len(val) >= 2 and val[0] == val[-1] and val[0] in {"'", '"'}:
            val = val[1:-1]
        os.environ.setdefault(key, val)


def env_str(key: str, default: str | None = None, required: bool = False) -> str:
    val = os.environ.get(key, default)
    if required and (val is None or val == ""):
        raise ValueError(f"Missing required env: {key}")
    return "" if val is None else str(val)


def env_int(key: str, default: int | None = None, required: bool = False) -> int:
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


def resolve_dir(raw: str, cwd: Path) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = cwd / path
    return path.resolve()


def scan_videos(video_dir: Path) -> List[Path]:
    """Return mp4 files from `video_dir`, sorted by name (no recursion)."""
    return sorted(
        [p for p in video_dir.iterdir() if p.is_file() and p.suffix.lower() == ".mp4"],
        key=lambda p: p.name.lower(),
    )
