import json
import platform
from pathlib import Path
from core.utils import BASE_DIR, get_api_key, get_api_key_safe

_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


def get_config() -> dict:
    return {"gemini_api_key": get_api_key()}


def _load_full_config() -> dict:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_os() -> str:
    """Returns: 'windows' | 'mac' | 'linux'"""
    _os_map = {"Windows": "windows", "Darwin": "mac", "Linux": "linux"}
    real_os = _os_map.get(platform.system(), "windows")
    try:
        config = _load_full_config()
        return config.get("os_system", real_os).lower()
    except Exception:
        return real_os


def is_windows() -> bool: return get_os() == "windows"
def is_mac()     -> bool: return get_os() == "mac"
def is_linux()   -> bool: return get_os() == "linux"
