import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from core.event_bus import EventType, get_bus
from core.runtime import get_runtime

logger = logging.getLogger("context_engine")


@dataclass
class ContextSnapshot:
    active_window: str = ""
    active_process: str = ""
    open_apps: list[str] = field(default_factory=list)
    screen_text: str = ""
    browser_url: str = ""
    browser_title: str = ""
    last_user_input: str = ""
    current_task: str = ""
    last_agent_thought: str = ""
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    battery: float = -1.0
    is_idle: bool = False
    idle_seconds: int = 0
    mode: str = "gemini"
    current_project: str = ""
    recent_actions: list[str] = field(default_factory=list)
    recent_errors: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


class ContextEngine:
    def __init__(self):
        self._bus = get_bus()
        self._runtime = get_runtime()
        self._current: ContextSnapshot = ContextSnapshot()
        self._history: list[ContextSnapshot] = []
        self._max_history = 100
        self._recent_actions: list[str] = []
        self._recent_errors: list[str] = []
        self._max_actions = 20
        self._listening = False

    def start(self):
        if self._listening:
            return
        self._listening = True
        self._bus.subscribe(EventType.USER_INPUT, self._on_user_input, source="context_engine")
        self._bus.subscribe(EventType.AGENT_ACTION, self._on_agent_action, source="context_engine")
        self._bus.subscribe(EventType.AGENT_THOUGHT, self._on_agent_thought, source="context_engine")
        self._bus.subscribe(EventType.ERROR_DETECTED, self._on_error, source="context_engine")
        self._bus.subscribe(EventType.APP_DETECTED, self._on_app_detected, source="context_engine")
        self._bus.subscribe(EventType.BROWSER_NAVIGATED, self._on_browser_nav, source="context_engine")
        logger.info("ContextEngine started")

    def stop(self):
        self._listening = False

    def _on_user_input(self, event):
        data = event.data
        text = data if isinstance(data, str) else (data.get("text", "") if isinstance(data, dict) else "")
        if text:
            self._current.last_user_input = text

    def _on_agent_action(self, event):
        data = event.data if isinstance(event.data, dict) else {}
        action_desc = data.get("result", str(data))[:100]
        self._recent_actions.append(action_desc)
        if len(self._recent_actions) > self._max_actions:
            self._recent_actions = self._recent_actions[-self._max_actions:]
        self._current.recent_actions = list(self._recent_actions)

    def _on_agent_thought(self, event):
        data = event.data if isinstance(event.data, dict) else {}
        thought = data.get("thought", "")
        if isinstance(thought, dict):
            thought = str(thought)
        self._current.last_agent_thought = str(thought)[:200]

    def _on_error(self, event):
        data = event.data if isinstance(event.data, dict) else {}
        error_msg = data.get("message", str(data))[:100]
        self._recent_errors.append(error_msg)
        if len(self._recent_errors) > 10:
            self._recent_errors = self._recent_errors[-10:]
        self._current.recent_errors = list(self._recent_errors)

    def _on_app_detected(self, event):
        data = event.data if isinstance(event.data, dict) else {}
        self._current.active_window = data.get("title", "")
        self._current.active_process = data.get("process", "")

    def _on_browser_nav(self, event):
        data = event.data if isinstance(event.data, dict) else {}
        self._current.browser_url = data.get("url", "")
        self._current.browser_title = data.get("title", "")

    def update(self):
        ctx = self._runtime.get_system_context()
        self._current.cpu_usage = ctx.get("cpu", 0)
        self._current.memory_usage = ctx.get("memory", 0)
        self._current.battery = ctx.get("battery", -1)
        self._current.is_idle = ctx.get("is_idle", False)
        self._current.idle_seconds = ctx.get("idle_seconds", 0)
        self._current.mode = ctx.get("mode", "gemini")
        self._current.open_apps = ctx.get("open_apps", [])

        snapshot = ContextSnapshot(
            active_window=self._current.active_window,
            active_process=self._current.active_process,
            open_apps=list(self._current.open_apps),
            screen_text=self._current.screen_text,
            browser_url=self._current.browser_url,
            browser_title=self._current.browser_title,
            last_user_input=self._current.last_user_input,
            current_task=self._current.current_task,
            last_agent_thought=self._current.last_agent_thought,
            cpu_usage=self._current.cpu_usage,
            memory_usage=self._current.memory_usage,
            battery=self._current.battery,
            is_idle=self._current.is_idle,
            idle_seconds=self._current.idle_seconds,
            mode=self._current.mode,
            recent_actions=list(self._recent_actions),
            recent_errors=list(self._recent_errors),
        )
        self._history.append(snapshot)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def get_context(self) -> ContextSnapshot:
        return self._current

    def get_context_string(self) -> str:
        c = self._current
        parts = [
            f"Janela ativa: {c.active_window} ({c.active_process})",
            f"Apps abertos: {', '.join(c.open_apps[:5]) if c.open_apps else 'Nenhum'}",
            f"CPU: {c.cpu_usage:.0f}% | RAM: {c.memory_usage:.0f}% | Bateria: {c.battery:.0f}%" if c.battery >= 0 else f"CPU: {c.cpu_usage:.0f}% | RAM: {c.memory_usage:.0f}%",
            f"Modo: {c.mode} | Ocioso: {c.is_idle} ({c.idle_seconds}s)",
            f"Último input: {c.last_user_input[:100] or 'Nenhum'}",
            f"Último pensamento: {c.last_agent_thought[:100] or 'Nenhum'}",
        ]
        if c.browser_url:
            parts.append(f"Navegador: {c.browser_title} - {c.browser_url[:80]}")
        if c.recent_actions:
            parts.append(f"Últimas ações: {'; '.join(c.recent_actions[-3:])}")
        if c.recent_errors:
            parts.append(f"Erros recentes: {'; '.join(c.recent_errors[-3:])}")
        return " | ".join(parts)

    def get_history(self, n: int = 5) -> list[ContextSnapshot]:
        return self._history[-n:]

    def clear(self):
        self._history.clear()
        self._recent_actions.clear()
        self._recent_errors.clear()


_context_engine_instance = None


def get_context_engine() -> ContextEngine:
    global _context_engine_instance
    if _context_engine_instance is None:
        _context_engine_instance = ContextEngine()
    return _context_engine_instance
