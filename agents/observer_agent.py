import logging
import time
from typing import Any, Optional

from agents.agent_base import BaseAgent
from core.event_bus import EventType, get_bus
from core.runtime import get_runtime

logger = logging.getLogger("observer_agent")


class ObserverAgent(BaseAgent):
    def __init__(self, interval: float = 5.0):
        super().__init__("observer", "Continuously observes desktop context and user activity")
        self.interval = interval
        self._last_active_window = ""
        self._last_screen_check = 0.0
        self._screen_check_interval = 30.0
        self._consecutive_idle = 0
        self._last_observation: dict = {}
        self._cycle_count = 0

    async def think(self, context: dict) -> Optional[dict]:
        self._cycle_count += 1
        observations = {}

        try:
            window_info = self._get_active_window()
            if window_info:
                observations["active_window"] = window_info
                if window_info.get("title") != self._last_active_window:
                    self._last_active_window = window_info.get("title", "")
                    self._bus.emit(EventType.APP_DETECTED, window_info, source=self.name)
        except Exception as e:
            observations["window_error"] = str(e)

        try:
            user_activity = self._check_user_activity()
            observations["user_activity"] = user_activity
        except Exception as e:
            observations["activity_error"] = str(e)

        try:
            app_list = self._list_open_apps()
            if app_list:
                observations["open_apps"] = app_list
                self._runtime.update_system(open_apps=app_list)
        except Exception as e:
            observations["apps_error"] = str(e)

        self._last_observation = observations

        if observations:
            self._bus.emit(EventType.OBSERVER_CYCLE, {
                "cycle": self._cycle_count,
                "observations": observations,
            }, source=self.name)

        return {
            "action": "observe",
            "cycle": self._cycle_count,
            "observations": observations,
        }

    async def act(self, thought: dict) -> Any:
        return thought

    def _get_active_window(self) -> Optional[dict]:
        try:
            import win32gui
            import win32process

            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)

            try:
                import psutil
                process = psutil.Process(pid)
                proc_name = process.name()
            except Exception:
                proc_name = f"PID:{pid}"

            info = {
                "title": title,
                "process": proc_name,
                "pid": pid,
                "detected_at": time.time(),
            }

            self._runtime.update_system(active_window=info)
            return info
        except Exception as e:
            return None

    def _check_user_activity(self) -> dict:
        try:
            import ctypes
            from ctypes import Structure, windll, c_uint, c_ulong

            class LASTINPUTINFO(Structure):
                _fields_ = [("cbSize", c_uint), ("dwTime", c_ulong)]

            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            windll.user32.GetLastInputInfo(ctypes.byref(lii))
            millis = windll.kernel32.GetTickCount() - lii.dwTime
            idle_seconds = millis // 1000

            is_idle = idle_seconds > 300
            self._runtime.update_system(
                is_idle=is_idle,
                idle_seconds=int(idle_seconds),
                last_user_activity=time.time(),
            )

            if is_idle:
                self._consecutive_idle += 1
            else:
                self._consecutive_idle = 0

            return {
                "idle_seconds": int(idle_seconds),
                "is_idle": is_idle,
                "consecutive_idle_cycles": self._consecutive_idle,
            }
        except Exception as e:
            return {"error": str(e)}

    def _list_open_apps(self) -> Optional[list[str]]:
        try:
            import win32gui

            apps = set()
            def enum_callback(hwnd, _):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title:
                        try:
                            import win32process
                            _, pid = win32process.GetWindowThreadProcessId(hwnd)
                            import psutil
                            process = psutil.Process(pid)
                            apps.add(process.name().replace(".exe", ""))
                        except Exception:
                            pass

            win32gui.EnumWindows(enum_callback, None)
            return sorted(apps)
        except Exception as e:
            return None

    def get_last_observation(self) -> dict:
        return dict(self._last_observation)

    def get_cycle_count(self) -> int:
        return self._cycle_count

    def subscribe_to_events(self):
        self.subscribe_to(
            EventType.USER_INPUT,
            EventType.APP_OPENED,
            EventType.APP_CLOSED,
            EventType.FILE_CHANGED,
        )

    async def observe(self, event) -> Optional[dict]:
        event_type = event.type
        if event_type == EventType.APP_OPENED:
            self.log(f"App opened: {event.data}")
        elif event_type == EventType.USER_INPUT:
            self._consecutive_idle = 0
        return {"event": event_type.value, "data": event.data}
