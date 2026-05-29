import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("desktop_automation")


class DesktopAutomation:
    def __init__(self):
        self._lock = threading.Lock()
        self._last_action_time = 0.0
        self._action_cooldown = 0.1

    def _wait_cooldown(self):
        elapsed = time.time() - self._last_action_time
        if elapsed < self._action_cooldown:
            time.sleep(self._action_cooldown - elapsed)

    def type_text(self, text: str, interval: float = 0.01):
        self._wait_cooldown()
        try:
            import pyautogui
            pyautogui.write(text, interval=interval)
            self._last_action_time = time.time()
            return True
        except Exception as e:
            logger.error(f"type_text failed: {e}")
            return False

    def click(self, x: Optional[int] = None, y: Optional[int] = None, button: str = "left", clicks: int = 1):
        self._wait_cooldown()
        try:
            import pyautogui
            if x is not None and y is not None:
                pyautogui.click(x=x, y=y, button=button, clicks=clicks)
            else:
                pyautogui.click(button=button, clicks=clicks)
            self._last_action_time = time.time()
            return True
        except Exception as e:
            logger.error(f"click failed: {e}")
            return False

    def double_click(self, x: Optional[int] = None, y: Optional[int] = None):
        return self.click(x, y, clicks=2)

    def right_click(self, x: Optional[int] = None, y: Optional[int] = None):
        return self.click(x, y, button="right")

    def move_mouse(self, x: int, y: int, duration: float = 0.3):
        self._wait_cooldown()
        try:
            import pyautogui
            pyautogui.moveTo(x, y, duration=duration)
            self._last_action_time = time.time()
            return True
        except Exception as e:
            logger.error(f"move_mouse failed: {e}")
            return False

    def drag_mouse(self, x: int, y: int, duration: float = 0.3):
        self._wait_cooldown()
        try:
            import pyautogui
            pyautogui.drag(x, y, duration=duration)
            self._last_action_time = time.time()
            return True
        except Exception as e:
            logger.error(f"drag_mouse failed: {e}")
            return False

    def scroll(self, amount: int = -1):
        self._wait_cooldown()
        try:
            import pyautogui
            pyautogui.scroll(amount)
            self._last_action_time = time.time()
            return True
        except Exception as e:
            logger.error(f"scroll failed: {e}")
            return False

    def press_key(self, key: str):
        self._wait_cooldown()
        try:
            import pyautogui
            pyautogui.press(key)
            self._last_action_time = time.time()
            return True
        except Exception as e:
            logger.error(f"press_key failed: {e}")
            return False

    def hotkey(self, *keys: str):
        self._wait_cooldown()
        try:
            import pyautogui
            pyautogui.hotkey(*keys)
            self._last_action_time = time.time()
            return True
        except Exception as e:
            logger.error(f"hotkey failed: {e}")
            return False

    def screenshot(self, path: str = "") -> Optional[str]:
        try:
            import pyautogui
            if path:
                img = pyautogui.screenshot(path)
            else:
                path = str(Path.home() / "Desktop" / f"screenshot_{int(time.time())}.png")
                img = pyautogui.screenshot(path)
            self._last_action_time = time.time()
            return path
        except Exception as e:
            logger.error(f"screenshot failed: {e}")
            return None

    def locate_on_screen(self, image_path: str, confidence: float = 0.8) -> Optional[tuple[int, int, int, int]]:
        try:
            import pyautogui
            result = pyautogui.locateOnScreen(image_path, confidence=confidence)
            return result
        except Exception as e:
            logger.error(f"locate_on_screen failed: {e}")
            return None

    def click_on_screen(self, image_path: str, confidence: float = 0.8) -> bool:
        pos = self.locate_on_screen(image_path, confidence)
        if pos:
            import pyautogui
            center = pyautogui.center(pos)
            return self.click(int(center.x), int(center.y))
        return False

    def get_mouse_position(self) -> Optional[tuple[int, int]]:
        try:
            import pyautogui
            return pyautogui.position()
        except Exception as e:
            logger.error(f"get_mouse_position failed: {e}")
            return None

    def get_screen_size(self) -> Optional[tuple[int, int]]:
        try:
            import pyautogui
            return pyautogui.size()
        except Exception as e:
            logger.error(f"get_screen_size failed: {e}")
            return None

    def focus_window(self, title: str):
        try:
            import pywinauto
            from pywinauto import Application
            app = Application().connect(title=title)
            app.top_window().set_focus()
            return True
        except Exception as e:
            logger.error(f"focus_window failed (pywinauto): {e}")
            try:
                import win32gui
                hwnd = win32gui.FindWindow(None, title)
                if hwnd:
                    win32gui.ShowWindow(hwnd, 5)
                    win32gui.SetForegroundWindow(hwnd)
                    return True
            except Exception as e2:
                logger.error(f"focus_window failed (win32): {e2}")
            return False

    def open_app(self, app_path: str) -> bool:
        try:
            subprocess.Popen(app_path, shell=False)
            return True
        except Exception as e:
            logger.error(f"open_app failed: {e}")
            return False

    def run_command(self, command: str) -> tuple[int, str, str]:
        try:
            result = subprocess.run(
                command, shell=False, capture_output=True, text=True, timeout=60
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Timeout"
        except Exception as e:
            return -1, "", str(e)

    def get_active_window_info(self) -> dict:
        try:
            import win32gui
            import win32process
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                import psutil
                proc = psutil.Process(pid)
                return {"title": title, "process": proc.name(), "pid": pid}
            except Exception:
                return {"title": title, "process": f"PID:{pid}", "pid": pid}
        except Exception as e:
            return {"error": str(e)}

    def list_windows(self) -> list[dict]:
        windows = []
        try:
            import win32gui
            def enum_callback(hwnd, _):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title:
                        windows.append({"hwnd": hwnd, "title": title})
            win32gui.EnumWindows(enum_callback, None)
        except Exception as e:
            logger.error(f"list_windows failed: {e}")
        return windows

    def __repr__(self):
        return "DesktopAutomation()"


_automation_instance = None
_automation_lock = threading.Lock()


def get_automation() -> DesktopAutomation:
    global _automation_instance
    with _automation_lock:
        if _automation_instance is None:
            _automation_instance = DesktopAutomation()
        return _automation_instance
