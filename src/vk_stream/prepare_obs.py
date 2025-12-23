from __future__ import annotations

import configparser
import json
import os
from pathlib import Path

from .common import env_int, env_str, load_dotenv


def main() -> int:
    cwd = Path.cwd()
    load_dotenv(cwd / ".env")

    port = env_int("OBS_PORT", default=4455)
    password = env_str("OBS_PASSWORD", "")

    config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    config_dir = config_root / "obs-studio"
    config_dir.mkdir(parents=True, exist_ok=True)
    global_ini = config_dir / "global.ini"

    parser = configparser.ConfigParser(strict=False)
    parser.optionxform = str
    if global_ini.exists():
        parser.read(global_ini)

    def ensure(section: str, items: dict) -> None:
        if section not in parser:
            parser[section] = {}
        for key, value in items.items():
            parser[section][key] = value

    enabled = "true"
    first_load = "false"
    auth_required = "true" if password else "false"

    # OBS 29+ (built-in obs-websocket 5)
    ensure(
        "WebSocketServer",
        {
            "ServerEnabled": enabled,
            "ServerPort": str(port),
            "ServerPassword": password,
            "AuthRequired": auth_required,
            "FirstLoad": first_load,
        },
    )

    # Legacy / alternative section names used by some builds
    ensure(
        "WebSocket",
        {
            "ServerEnabled": enabled,
            "ServerPort": str(port),
            "ServerPassword": password,
            "FirstLoad": first_load,
        },
    )
    ensure(
        "OBSWebSocket",
        {
            "ServerEnabled": enabled,
            "ServerPort": str(port),
            "ServerPassword": password,
            "AlertsEnabled": "false",
            "AuthRequired": auth_required,
            "FirstLoad": first_load,
        },
    )
    ensure(
        "obs-websocket",
        {
            "server_enabled": enabled,
            "server_port": str(port),
            "server_password": password,
            "auth_required": auth_required,
            "first_load": first_load,
        },
    )

    with global_ini.open("w", encoding="utf-8") as fh:
        parser.write(fh)

    # obs-websocket v5 stores settings in a JSON config file; write a few
    # common locations/keys to maximize compatibility across builds.
    obsws_payload = {
        "server_enabled": True,
        "server_port": port,
        "auth_required": bool(password),
        "first_load": False,
        "server_password": password,
    }

    candidate_dirs = [
        config_dir / "plugin_config" / "obs-websocket",
        config_dir / "obs-websocket",
        config_dir / "config" / "obs-websocket",
    ]
    for obsws_dir in candidate_dirs:
        obsws_dir.mkdir(parents=True, exist_ok=True)
        with (obsws_dir / "config.json").open("w", encoding="utf-8") as fh:
            json.dump(obsws_payload, fh, ensure_ascii=False, indent=2)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
