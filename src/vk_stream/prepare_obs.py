from __future__ import annotations

import configparser
from pathlib import Path

from .common import env_int, env_str, load_dotenv


def main() -> int:
    cwd = Path.cwd()
    load_dotenv(cwd / ".env")

    port = env_int("OBS_PORT", default=4455)
    password = env_str("OBS_PASSWORD", "")

    config_dir = Path.home() / ".config" / "obs-studio"
    config_dir.mkdir(parents=True, exist_ok=True)
    global_ini = config_dir / "global.ini"

    parser = configparser.ConfigParser()
    parser.optionxform = str
    if global_ini.exists():
        parser.read(global_ini)

    if "WebSocket" not in parser:
        parser["WebSocket"] = {}

    parser["WebSocket"]["ServerEnabled"] = "true"
    parser["WebSocket"]["ServerPort"] = str(port)
    parser["WebSocket"]["ServerPassword"] = password

    with global_ini.open("w", encoding="utf-8") as fh:
        parser.write(fh)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
