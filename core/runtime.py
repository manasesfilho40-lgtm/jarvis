import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("runtime")


@dataclass
class ActiveWindow:
    title: str = ""
    process: str = ""
    pid: int = 0
    detected_at: float = 0.0


@dataclass
class SystemContext:
    screen_resolution: tuple[int, int] = (0, 0)
    active_window: ActiveWindow = field(default_factory=ActiveWindow)
    open_apps: list[str] = field(default_factory=list)
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    battery_percent: float = -1.0
    uptime: float = 0.0
    network_connected: bool = True
    last_user_activity: float = 0.0
    is_idle: bool = False
    idle_seconds: int = 0


@dataclass
class RuntimeState:
    mode: str = "gemini"
    is_speaking: bool = False
    is_listening: bool = False
    is_muted: bool = False
    is_processing: bool = False
    is_night_mode: bool = False
    current_provider: str = "gemini"
    current_model: str = "gemini-2.5-flash-lite"
    ollama_model: str = "qwen2.5:7b"
    tasks_running: int = 0
    tasks_pending: int = 0
    agents_active: list[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)


class Runtime:
    def __init__(self):
        self._system = SystemContext()
        self._state = RuntimeState()
        self._lock = threading.Lock()
        self._observers: dict[str, callable] = {}
        self._variables: dict[str, Any] = {}
        self._event_history: list[dict] = []
        self._max_event_history = 500

    @property
    def state(self) -> RuntimeState:
        return self._state

    @property
    def system(self) -> SystemContext:
        return self._system

    def update_system(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self._system, k):
                    setattr(self._system, k, v)
            if "active_window" in kwargs:
                win = kwargs["active_window"]
                if isinstance(win, dict):
                    self._system.active_window = ActiveWindow(**win)

    def update_state(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self._state, k):
                    setattr(self._state, k, v)
            self._notify("state_changed", {k: v for k, v in kwargs.items() if hasattr(self._state, k)})

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            if hasattr(self._state, key):
                return getattr(self._state, key)
            if hasattr(self._system, key):
                return getattr(self._system, key)
            return self._variables.get(key, default)

    def set(self, key: str, value: Any):
        with self._lock:
            if hasattr(self._state, key):
                setattr(self._state, key, value)
            elif hasattr(self._system, key):
                setattr(self._system, key, value)
            else:
                self._variables[key] = value
            self._notify("var_changed", {"key": key, "value": value})

    def observe(self, key: str, callback: callable):
        self._observers[key] = callback

    def _notify(self, event: str, data: dict):
        self._event_history.append({"event": event, "data": data, "time": time.time()})
        if len(self._event_history) > self._max_event_history:
            self._event_history = self._event_history[-self._max_event_history:]
        callback = self._observers.get(event)
        if callback:
            try:
                callback(data)
            except Exception as e:
                logger.error(f"Runtime observer '{event}' failed: {e}")

    def get_active_window_info(self) -> str:
        win = self._system.active_window
        if win.title:
            return f"{win.process}: {win.title}"
        return "Unknown"

    def get_system_context(self) -> dict:
        return {
            "active_window": self.get_active_window_info(),
            "open_apps": self._system.open_apps,
            "cpu": self._system.cpu_usage,
            "memory": self._system.memory_usage,
            "battery": self._system.battery_percent,
            "uptime": time.time() - self._state.started_at,
            "mode": self._state.mode,
            "model": self._state.current_model,
            "is_idle": self._system.is_idle,
            "idle_seconds": self._system.idle_seconds,
            "tasks": {
                "running": self._state.tasks_running,
                "pending": self._state.tasks_pending,
            },
            "agents": list(self._state.agents_active),
        }

    def get_context_string(self) -> str:
        ctx = self.get_system_context()
        parts = [
            f"Mode: {ctx['mode']}",
            f"Model: {ctx['model']}",
            f"Active: {ctx['active_window']}",
            f"Tasks running: {ctx['tasks']['running']}",
            f"Tasks pending: {ctx['tasks']['pending']}",
            f"Agents active: {', '.join(ctx['agents']) if ctx['agents'] else 'None'}",
            f"Idle: {ctx['is_idle']} ({ctx['idle_seconds']}s)",
        ]
        return " | ".join(parts)

    def get_uptime_string(self) -> str:
        seconds = int(time.time() - self._state.started_at)
        h, m = divmod(seconds, 3600)
        m, s = divmod(m, 60)
        return f"{h}h {m}m {s}s"

    def __repr__(self):
        return f"Runtime(mode={self._state.mode}, uptime={self.get_uptime_string()})"


_runtime_instance = None
_runtime_lock = threading.Lock()


def get_runtime() -> Runtime:
    global _runtime_instance
    with _runtime_lock:
        if _runtime_instance is None:
            _runtime_instance = Runtime()
        return _runtime_instance
