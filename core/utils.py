import json
import sys
from pathlib import Path


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


def get_api_key() -> str:
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data["gemini_api_key"]
    except (KeyError, FileNotFoundError, json.JSONDecodeError):
        return ""


def get_api_key_safe() -> str:
    try:
        return get_api_key()
    except Exception:
        return ""

# Fila compartilhada de comandos (evita import circular entre ui.py e web_server.py)
import threading

class _ThreadSafeCommandQueue:
    def __init__(self):
        self._queue: list = []
        self._lock = threading.Lock()

    def append(self, cmd: str):
        with self._lock:
            self._queue.append(cmd)

    def pop(self, index: int = 0) -> str:
        with self._lock:
            return self._queue.pop(index)

    def __len__(self) -> int:
        with self._lock:
            return len(self._queue)

    def __bool__(self) -> bool:
        return len(self) > 0

    def copy(self) -> list:
        with self._lock:
            return list(self._queue)

global_command_queue: _ThreadSafeCommandQueue = _ThreadSafeCommandQueue()
