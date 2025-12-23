#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

try:
    from obsws_python import ReqClient

    _OBS_REQ_CLIENT = True
except Exception:  # pragma: no cover - fallback for older obsws-python
    from obsws_python import obsws, requests as obs_requests

    _OBS_REQ_CLIENT = False

from .common import (
    EP_RE,
    env_bool,
    env_int,
    env_str,
    load_dotenv,
    parse_exts,
    scan_videos,
)


@dataclass
class Config:
    vk_url: str
    vk_key: str
    video_dir: Path
    start_ep: str
    loop: bool
    loglevel: str
    ffprobe_path: str
    video_exts: List[str]
    audio_index: int
    sub_si: int
    video_bitrate: str
    audio_bitrate: str
    preset: str
    gop: int
    audio_rate: str
    audio_channels: int
    obs_host: str
    obs_port: int
    obs_password: str
    obs_scene: str
    obs_vlc_source: str
    obs_text_source: str

    @classmethod
    def from_env(cls, cwd: Path) -> "Config":
        vk_url = env_str("VK_URL", required=True)
        vk_key = env_str("VK_KEY", required=True)
        video_dir = env_str("VIDEO_DIR", required=True)
        start_ep = env_str("START_EP", "")

        video_dir_path = Path(video_dir).expanduser()
        if not video_dir_path.is_absolute():
            video_dir_path = cwd / video_dir_path
        video_dir_path = video_dir_path.resolve()

        return cls(
            vk_url=vk_url,
            vk_key=vk_key,
            video_dir=video_dir_path,
            start_ep=start_ep,
            loop=env_bool("LOOP", True),
            loglevel=env_str("LOGLEVEL", "info"),
            ffprobe_path=env_str("FFPROBE_PATH", "ffprobe"),
            video_exts=parse_exts(env_str("VIDEO_EXTS", ".mkv")),
            audio_index=env_int("AUDIO_INDEX", default=1),
            sub_si=env_int("SUB_SI", default=1),
            video_bitrate=env_str("STREAM_VIDEO_BITRATE", "3000k"),
            audio_bitrate=env_str("STREAM_AUDIO_BITRATE", "160k"),
            preset=env_str("STREAM_PRESET", "superfast"),
            gop=env_int("STREAM_GOP", default=48),
            audio_rate=env_str("STREAM_AUDIO_RATE", "48000"),
            audio_channels=env_int("STREAM_AUDIO_CHANNELS", default=2),
            obs_host=env_str("OBS_HOST", "127.0.0.1"),
            obs_port=env_int("OBS_PORT", default=4455),
            obs_password=env_str("OBS_PASSWORD", ""),
            obs_scene=env_str("OBS_SCENE", "Scene"),
            obs_vlc_source=env_str("OBS_VLC_SOURCE", "VLC"),
            obs_text_source=env_str("OBS_TEXT_SOURCE", "NowPlaying"),
        )


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def parse_ratio(raw: str) -> Tuple[int, int]:
    if "/" in raw:
        num, den = raw.split("/", 1)
        return int(num), int(den)
    return int(float(raw) * 1000), 1000


def parse_bitrate_kbps(raw: str) -> int:
    val = raw.strip().lower()
    if val.endswith("k"):
        return int(float(val[:-1]))
    if val.endswith("m"):
        return int(float(val[:-1]) * 1000)
    return int(float(val))


def ffprobe_video_info(cfg: Config, path: Path) -> Tuple[int, int, int, int]:
    cmd = [
        cfg.ffprobe_path,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate",
        "-of",
        "json",
        str(path),
    ]
    out = subprocess.check_output(cmd, text=True)
    data = json.loads(out)
    stream = data["streams"][0]
    width = int(stream["width"])
    height = int(stream["height"])
    fps_num, fps_den = parse_ratio(stream.get("r_frame_rate", "24/1"))
    return width, height, fps_num, fps_den


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


def resp_get(obj, key: str, default=None):
    if hasattr(obj, key):
        return getattr(obj, key)
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def item_get(obj, key: str, default=None):
    if hasattr(obj, key):
        return getattr(obj, key)
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def _to_snake(name: str) -> str:
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


class ObsClient:
    def __init__(self, host: str, port: int, password: str, timeout: float = 5.0):
        self._req_client = _OBS_REQ_CLIENT
        if self._req_client:
            self._ws = ReqClient(host=host, port=port, password=password, timeout=timeout)
        else:
            self._ws = obsws(host=host, port=port, password=password)

    def connect(self) -> None:
        if not self._req_client:
            self._ws.connect()

    def disconnect(self) -> None:
        if not self._req_client:
            self._ws.disconnect()

    def call(self, name: str, **kwargs):
        if self._req_client:
            method = _to_snake(name)
            func = getattr(self._ws, method)
            return func(**kwargs)
        req_cls = getattr(obs_requests, name)
        return self._ws.call(req_cls(**kwargs))


def connect_obs(cfg: Config, retries: int = 60, delay: float = 1.0) -> ObsClient:
    last_err: Optional[Exception] = None
    for _ in range(retries):
        try:
            ws = ObsClient(cfg.obs_host, cfg.obs_port, cfg.obs_password)
            ws.connect()
            ws.call("GetVersion")
            return ws
        except Exception as exc:
            last_err = exc
            time.sleep(delay)
    raise RuntimeError(f"OBS websocket not reachable: {last_err}")


def ensure_scene(ws: ObsClient, scene_name: str) -> None:
    resp = ws.call("GetSceneList")
    scenes = resp_get(resp, "scenes", []) or []
    if not any(item_get(s, "sceneName") == scene_name for s in scenes):
        ws.call("CreateScene", sceneName=scene_name)


def ensure_input(
    ws: ObsClient,
    scene_name: str,
    input_name: str,
    input_kind: str,
    input_settings: dict,
    enabled: bool = True,
) -> None:
    resp = ws.call("GetInputList")
    inputs = resp_get(resp, "inputs", []) or []
    if any(item_get(i, "inputName") == input_name for i in inputs):
        ws.call(
            "SetInputSettings",
            inputName=input_name,
            inputSettings=input_settings,
            overlay=False,
        )
    else:
        ws.call(
            "CreateInput",
            sceneName=scene_name,
            inputName=input_name,
            inputKind=input_kind,
            inputSettings=input_settings,
            sceneItemEnabled=enabled,
        )


def set_scene_item_pos(ws: ObsClient, scene_name: str, source_name: str, x: float, y: float) -> None:
    resp = ws.call("GetSceneItemId", sceneName=scene_name, sourceName=source_name)
    item_id = resp_get(resp, "sceneItemId")
    if item_id is None:
        return
    ws.call(
        "SetSceneItemTransform",
        sceneName=scene_name,
        sceneItemId=item_id,
        sceneItemTransform={"positionX": x, "positionY": y},
    )


def configure_stream(ws: ObsClient, cfg: Config) -> None:
    ws.call(
        "SetStreamServiceSettings",
        streamServiceType="rtmp_custom",
        streamServiceSettings={"server": cfg.vk_url, "key": cfg.vk_key},
    )

    resp = ws.call("GetOutputList")
    outputs = resp_get(resp, "outputs", []) or []
    output_name = None
    for out in outputs:
        kind = str(item_get(out, "outputKind", "")).lower()
        name = item_get(out, "outputName")
        if "rtmp" in kind or "stream" in str(name).lower():
            output_name = name
            break

    if not output_name:
        log("WARN: could not find streaming output to configure")
        return

    settings_resp = ws.call("GetOutputSettings", outputName=output_name)
    settings = resp_get(settings_resp, "outputSettings", {}) or {}
    updated = dict(settings)

    v_kbps = parse_bitrate_kbps(cfg.video_bitrate)
    a_kbps = parse_bitrate_kbps(cfg.audio_bitrate)

    for key in (
        "bitrate",
        "VBitrate",
        "video_bitrate",
        "vbitrate",
        "bitrate_kbps",
        "target_bitrate",
    ):
        if key in updated:
            updated[key] = v_kbps

    for key in ("audio_bitrate", "ABitrate", "aBitrate", "audioBitrate"):
        if key in updated:
            updated[key] = a_kbps

    for key in ("preset", "x264_preset", "Preset"):
        if key in updated:
            updated[key] = cfg.preset

    if updated != settings:
        ws.call(
            "SetOutputSettings",
            outputName=output_name,
            outputSettings=updated,
        )


def ensure_streaming(ws: ObsClient) -> None:
    resp = ws.call("GetStreamStatus")
    active = resp_get(resp, "outputActive", False)
    if not active:
        ws.call("StartStream")


def update_vlc_source(ws: ObsClient, cfg: Config, input_path: Path) -> None:
    settings = {
        "playlist": [{"value": str(input_path), "hidden": False}],
        "loop": False,
        "shuffle": False,
        "audio_track": cfg.audio_index,
        "subtitle_track": cfg.sub_si,
    }
    ws.call(
        "SetInputSettings",
        inputName=cfg.obs_vlc_source,
        inputSettings=settings,
        overlay=False,
    )
    try:
        ws.call(
            "TriggerMediaInputAction",
            inputName=cfg.obs_vlc_source,
            mediaAction="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART",
        )
    except Exception:
        pass


def update_text(ws: ObsClient, cfg: Config, title: str) -> None:
    settings = {
        "text": title,
        "font": {"face": "DejaVu Sans", "size": 36, "style": "Regular"},
        "color1": 4294967295,
        "outline": True,
        "outline_size": 2,
        "outline_color": 4278190080,
    }
    ws.call(
        "SetInputSettings",
        inputName=cfg.obs_text_source,
        inputSettings=settings,
        overlay=False,
    )


def wait_for_media_end(ws: ObsClient, cfg: Config, stop_flag) -> int:
    while not stop_flag():
        resp = ws.call("GetMediaInputStatus", inputName=cfg.obs_vlc_source)
        state = resp_get(resp, "mediaState", "")
        if state in {
            "OBS_MEDIA_STATE_ENDED",
            "OBS_MEDIA_STATE_STOPPED",
            "OBS_MEDIA_STATE_NONE",
        }:
            return 0
        if state == "OBS_MEDIA_STATE_ERROR":
            return 2
        time.sleep(1)
    return 0


def stream_files(cfg: Config, files: List[Path], dry_run: bool) -> int:
    if not files:
        log("No video files found.")
        return 2

    start_idx = find_start_index(files, cfg.start_ep)
    if cfg.start_ep and start_idx is None:
        log(f"WARN: START_EP not found: {cfg.start_ep}")
        start_idx = 0

    width, height, fps_num, fps_den = ffprobe_video_info(cfg, files[0])

    ws = connect_obs(cfg)
    stop = False

    def handle(_sig: int, _frame) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGINT, handle)

    ensure_scene(ws, cfg.obs_scene)

    vlc_settings = {
        "playlist": [{"value": str(files[0]), "hidden": False}],
        "loop": False,
        "shuffle": False,
        "audio_track": cfg.audio_index,
        "subtitle_track": cfg.sub_si,
    }
    ensure_input(ws, cfg.obs_scene, cfg.obs_vlc_source, "vlc_source", vlc_settings)

    text_settings = {
        "text": title_for_path(files[0]),
        "font": {"face": "DejaVu Sans", "size": 36, "style": "Regular"},
        "color1": 4294967295,
        "outline": True,
        "outline_size": 2,
        "outline_color": 4278190080,
    }
    ensure_input(ws, cfg.obs_scene, cfg.obs_text_source, "text_ft2_source", text_settings)
    set_scene_item_pos(ws, cfg.obs_scene, cfg.obs_text_source, 20, 20)

    ws.call(
        "SetVideoSettings",
        baseWidth=width,
        baseHeight=height,
        outputWidth=width,
        outputHeight=height,
        fpsNumerator=fps_num,
        fpsDenominator=fps_den,
    )
    configure_stream(ws, cfg)

    if dry_run:
        log("Dry run: OBS configured, not starting stream.")
        return 0

    ensure_streaming(ws)

    first_pass = True
    try:
        while True:
            if first_pass and start_idx:
                order = files[start_idx:] + files[:start_idx]
            else:
                order = files

            for idx, f in enumerate(order, start=1):
                if stop:
                    return 0
                log(f"Playing {idx}/{len(order)}: {f}")
                update_text(ws, cfg, title_for_path(f))
                update_vlc_source(ws, cfg, f)
                code = wait_for_media_end(ws, cfg, lambda: stop)
                if code != 0:
                    return code

            if not cfg.loop:
                break
            first_pass = False
    finally:
        try:
            if resp_get(ws.call("GetStreamStatus"), "outputActive", False):
                ws.call("StopStream")
        except Exception:
            pass
        try:
            ws.disconnect()
        except Exception:
            pass

    return 0


def main(argv: Optional[List[str]] = None) -> int:
    cwd = Path.cwd()
    load_dotenv(cwd / ".env")

    parser = argparse.ArgumentParser(description="OBS-based VK streamer (VLC source)")
    parser.add_argument("--dry-run", action="store_true", help="Configure OBS and exit")
    args = parser.parse_args(argv)

    try:
        cfg = Config.from_env(cwd)
    except Exception as exc:
        log(f"Config error: {exc}")
        return 2

    if not cfg.video_dir.exists():
        log(f"VIDEO_DIR does not exist: {cfg.video_dir}")
        return 2

    files = scan_videos(cfg.video_dir, cfg.video_exts)
    return stream_files(cfg, files, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
