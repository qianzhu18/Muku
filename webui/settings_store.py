import json
import os
import sys
import uuid
from pathlib import Path


APP_CONFIG_DIRNAME = "video-downloade"
SETTINGS_FILENAME = "settings.json"


def config_dir() -> Path:
    configured = os.environ.get("VIDEO_DOWNLOADE_CONFIG_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()

    if os.name == "nt":
        appdata = os.environ.get("APPDATA", "").strip()
        if appdata:
            return Path(appdata) / APP_CONFIG_DIRNAME

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_CONFIG_DIRNAME

    xdg_config_home = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if xdg_config_home:
        return Path(xdg_config_home).expanduser() / APP_CONFIG_DIRNAME

    return Path.home() / ".config" / APP_CONFIG_DIRNAME


def settings_path() -> Path:
    return config_dir() / SETTINGS_FILENAME


def load_settings() -> dict:
    path = settings_path()
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    return payload if isinstance(payload, dict) else {}


def save_settings(settings: dict) -> Path:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp_path.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)
    return path
