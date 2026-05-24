import asyncio
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional

from core.event_bus import EventBus, EventType, get_bus, emit
from core.runtime import Runtime, get_runtime

logger = logging.getLogger("system_bridge")


class SystemBridge:
    def __init__(self):
        self._bus: EventBus = get_bus()
        self._runtime: Runtime = get_runtime()
        self._initialized = False
        self._orchestrator = None
        self._continuous_loop = None
        self._provider_manager = None
        self._vector_memory = None
        self._ui_bridge = None
        self._hooks: dict[str, list[callable]] = {}

    def initialize(self, ui=None, config_path: str = ""):
        if self._initialized:
            return

        self._bridge_ui(ui)

        self._init_observers()

        self._initialized = True
        self._runtime.update_state(started_at=time.time())
        emit(EventType.SYSTEM_STARTUP, {
            "bridge": "initialized",
            "timestamp": time.time(),
        }, source="system_bridge")
        logger.info("System Bridge initialized")

    def _bridge_ui(self, ui):
        if ui is None:
            return

        self._ui_bridge = ui

        def ui_log_handler(event):
            if hasattr(ui, 'write_log') and event.data:
                ui.write_log(str(event.data))

        self._bus.subscribe(EventType.UI_LOG_MESSAGE, ui_log_handler, source="bridge")
        self._bus.subscribe(EventType.AGENT_THOUGHT, ui_log_handler, source="bridge")
        self._bus.subscribe(EventType.THOUGHT_STREAM, ui_log_handler, source="bridge")

        def ui_state_handler(event):
            state = event.data.get("state", "") if isinstance(event.data, dict) else ""
            if state and hasattr(ui, 'set_state'):
                ui.set_state(state)

        self._bus.subscribe(EventType.UI_STATE_CHANGED, ui_state_handler, source="bridge")

    def _init_observers(self):
        self._bus.subscribe(EventType.OBSERVER_CYCLE, self._on_observer_cycle, source="bridge")
        self._bus.subscribe(EventType.AGENT_ERROR, self._on_agent_error, source="bridge")
        self._bus.subscribe(EventType.SYSTEM_ERROR, self._on_system_error, source="bridge")

    def _on_observer_cycle(self, event):
        observations = event.data.get("observations", {}) if isinstance(event.data, dict) else {}
        if observations.get("active_window"):
            win = observations["active_window"]
            logger.debug(f"Active window: {win.get('process')} - {win.get('title')}")

    def _on_agent_error(self, event):
        data = event.data if isinstance(event.data, dict) else {}
        logger.warning(f"Agent error: {data.get('agent')} - {data.get('error')}")

    def _on_system_error(self, event):
        data = event.data if isinstance(event.data, dict) else {}
        logger.error(f"System error: {data.get('error')}")
        emit(EventType.UI_LOG_MESSAGE, f"ERR: {data.get('error', 'Unknown error')}", source="system_bridge")

    def hook(self, name: str, callback: callable):
        if name not in self._hooks:
            self._hooks[name] = []
        self._hooks[name].append(callback)

    def trigger_hook(self, name: str, *args, **kwargs):
        for cb in self._hooks.get(name, []):
            try:
                cb(*args, **kwargs)
            except Exception as e:
                logger.error(f"Hook '{name}' failed: {e}")

    def get_runtime_context(self) -> str:
        return self._runtime.get_context_string()

    def get_system_stats(self) -> dict:
        stats = {
            "runtime": self._runtime.get_system_context(),
            "events": {
                "total": sum(self._bus.get_stats().values()),
                "subscribers": self._bus.get_subscriber_count(),
            },
            "agents": self._orchestrator.get_status_summary() if self._orchestrator else {},
            "loop": self._continuous_loop.get_stats() if self._continuous_loop else {},
        }
        return stats

    def __repr__(self):
        return f"SystemBridge(initialized={self._initialized})"


_bridge_instance = None
_bridge_lock = threading.Lock()


def get_bridge() -> SystemBridge:
    global _bridge_instance
    with _bridge_lock:
        if _bridge_instance is None:
            _bridge_instance = SystemBridge()
        return _bridge_instance
