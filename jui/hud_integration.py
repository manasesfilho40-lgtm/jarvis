import asyncio
import json
import logging
import os
import subprocess
import threading
from typing import Optional

from core.event_bus import EventBus, EventType, get_bus
from jui.hud_overlay import HUDOverlay, HUDMessage, AgentThought, init_hud

logger = logging.getLogger("hud_integration")

_HUD_REF = [None]
_INTEGRATION_DONE = [False]


def integrate_hud(ui_obj=None) -> Optional["HUDOverlay"]:
    if _INTEGRATION_DONE[0]:
        return _HUD_REF[0]

    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if not app:
            logger.warning("No QApplication instance found for HUD")
            return None

        hud = init_hud(app)
        if not hud:
            return None

        _HUD_REF[0] = hud
        _INTEGRATION_DONE[0] = True

        hud.show_overlay()

        _connect_event_bus(hud)

        logger.info("HUD integrated with existing UI")
        return hud

    except Exception as e:
        logger.error(f"HUD integration failed: {e}")
        return None


def _connect_event_bus(hud: HUDOverlay):
    try:
        bus = get_bus()

        def on_thought(event):
            data = event.data
            source = event.source
            agent = data.get("agent", source) if isinstance(data, dict) else source
            thought = data.get("thought", str(data)) if isinstance(data, dict) else str(data)
            hud.push_thought(agent, thought[:200])

        bus.subscribe(EventType.AGENT_THOUGHT, on_thought, source="hud")
        bus.subscribe(EventType.THOUGHT_STREAM, on_thought, source="hud")

        def on_message(event):
            data = event.data
            text = data.get("message", str(data)) if isinstance(data, dict) else str(data)
            level = data.get("level", "info") if isinstance(data, dict) else "info"
            duration = data.get("duration", 5.0) if isinstance(data, dict) else 5.0
            hud.push_message(text, source=event.source, level=level, duration=duration)

        bus.subscribe(EventType.UI_LOG_MESSAGE, on_message, source="hud")
        bus.subscribe(EventType.UI_NOTIFICATION, on_message, source="hud")

        def on_runtime_update(event):
            data = event.data
            if isinstance(data, dict):
                hud.update_status(data)

        bus.subscribe(EventType.UI_STATE_CHANGED, on_runtime_update, source="hud")
        bus.subscribe(EventType.SYSTEM_STARTUP, on_runtime_update, source="hud")
        bus.subscribe(EventType.OBSERVER_CYCLE, on_runtime_update, source="hud")

        logger.info("HUD connected to EventBus")

    except Exception as e:
        logger.warning(f"HUD EventBus connection skipped: {e}")


def hud_status_updater(interval: float = 1.0):
    def _run():
        import time
        while True:
            hud = _HUD_REF[0]
            if hud:
                try:
                    from core.event_bus import get_bus
                    bus = get_bus()
                    stats = bus.get_stats()
                    subs = bus.get_subscriber_count()
                    hud.update_status({
                        "events": dict(stats) if stats else {},
                        "subscribers": subs,
                        "agents_active": ["observer", "vision", "reflection", "browser"],
                        "current_phase": "idle",
                        "cycle_count": 0,
                    })
                except Exception:
                    pass
            time.sleep(interval)

    threading.Thread(target=_run, daemon=True, name="hud-status").start()


def get_hud() -> Optional["HUDOverlay"]:
    return _HUD_REF[0]
