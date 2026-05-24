import asyncio
import json
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("hud_overlay")


try:
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRect, QPoint, QPointF, QSize
    from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QFontMetrics, QPainterPath, QLinearGradient
    from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
    HAS_PYQT6 = True
except ImportError:
    HAS_PYQT6 = False
    logger.warning("PyQt6 not available for HUD overlay")


try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


@dataclass
class HUDMessage:
    text: str
    source: str = "system"
    level: str = "info"
    timestamp: float = field(default_factory=time.time)
    duration: float = 5.0

    def is_expired(self) -> bool:
        return time.time() - self.timestamp > self.duration


@dataclass
class AgentThought:
    agent: str
    thought: str
    timestamp: float = field(default_factory=time.time)


class HUDOverlay(QWidget):
    def __init__(self, parent=None, opacity: float = 0.85):
        super().__init__(parent)
        if not HAS_PYQT6:
            return

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet("background: transparent;")

        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            self._screen_width = geo.width()
            self._screen_height = geo.height()
        else:
            self._screen_width = 1920
            self._screen_height = 1080

        self._panel_width = 380
        self._panel_height = self._screen_height - 100
        self.setGeometry(
            self._screen_width - self._panel_width - 20,
            50,
            self._panel_width,
            self._panel_height,
        )

        self._opacity = opacity
        self._messages: list[HUDMessage] = []
        self._thoughts: list[AgentThought] = []
        self._system_status: dict = {}
        self._waveform_data: list[float] = [0.0] * 60
        self._active_agents: list[str] = []
        self._current_phase: str = "idle"
        self._cycle_count: int = 0
        self._max_messages = 20
        self._max_thoughts = 10
        self._visible = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update)
        self._timer.start(50)

        self._message_queue: queue.Queue = queue.Queue()

    def show_overlay(self):
        self.show()
        self._visible = True
        self.raise_()
        logger.info("HUD overlay shown")

    def hide_overlay(self):
        self.hide()
        self._visible = False
        logger.info("HUD overlay hidden")

    def toggle(self):
        if self._visible:
            self.hide_overlay()
        else:
            self.show_overlay()

    def push_message(self, text: str, source: str = "system", level: str = "info", duration: float = 5.0):
        self._message_queue.put(HUDMessage(
            text=text, source=source,
            level=level, duration=duration,
        ))

    def push_thought(self, agent: str, thought: str):
        self._thoughts.insert(0, AgentThought(agent=agent, thought=thought))
        if len(self._thoughts) > self._max_thoughts:
            self._thoughts = self._thoughts[:self._max_thoughts]

    def update_status(self, status: dict):
        self._system_status = status
        if "agents_active" in status:
            self._active_agents = status["agents_active"]
        if "current_phase" in status:
            self._current_phase = status["current_phase"]
        if "cycle_count" in status:
            self._cycle_count = status["cycle_count"]

    def update_waveform(self, data: list[float]):
        self._waveform_data = (data + self._waveform_data)[:60]

    def _update(self):
        while not self._message_queue.empty():
            try:
                msg = self._message_queue.get_nowait()
                self._messages.append(msg)
                if len(self._messages) > self._max_messages:
                    self._messages = self._messages[-self._max_messages:]
            except queue.Empty:
                break

        self._messages = [m for m in self._messages if not m.is_expired()]
        self.update()

    def paintEvent(self, event):
        if not HAS_PYQT6:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self._draw_background(painter)
        self._draw_header(painter)
        self._draw_thoughts(painter)
        self._draw_messages(painter)
        self._draw_status_bar(painter)
        self._draw_waveform(painter)

        painter.end()

    def _draw_background(self, painter):
        rect = self.rect()
        gradient = QLinearGradient(QPointF(rect.topLeft()), QPointF(rect.bottomLeft()))
        gradient.setColorAt(0.0, QColor(10, 15, 30, int(230 * self._opacity)))
        gradient.setColorAt(1.0, QColor(5, 10, 20, int(200 * self._opacity)))
        painter.fillRect(rect, QBrush(gradient))

        painter.setPen(QPen(QColor(0, 150, 255, 80), 1))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)

    def _draw_header(self, painter):
        painter.setPen(QColor(0, 180, 255))
        font = QFont("Segoe UI", 13, QFont.Weight.Bold)
        painter.setFont(font)

        phase_colors = {
            "observe": QColor(0, 200, 255),
            "think": QColor(255, 200, 0),
            "plan": QColor(0, 255, 100),
            "execute": QColor(255, 100, 0),
            "reflect": QColor(180, 0, 255),
            "learn": QColor(0, 255, 200),
            "idle": QColor(100, 100, 100),
        }
        phase_color = phase_colors.get(self._current_phase, QColor(0, 180, 255))

        painter.setPen(phase_color)
        painter.drawText(15, 28, f"J.A.R.V.I.S  •  Cycle #{self._cycle_count}")

        painter.setPen(QColor(100, 180, 255, 150))
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(15, 46, f"Phase: {self._current_phase.upper()}")

    def _draw_thoughts(self, painter):
        y_base = 60
        painter.setPen(QColor(150, 200, 255, 200))
        font = QFont("Consolas", 8)
        painter.setFont(font)

        for thought in self._thoughts[:5]:
            lines = self._wrap_text(f"[{thought.agent}] {thought.thought}", 360)
            for line in lines:
                painter.drawText(15, y_base, line)
                y_base += 14
            y_base += 4

        self._thoughts_draw_end = y_base

    def _draw_messages(self, painter):
        y_base = max(self._thoughts_draw_end + 10, 180)
        painter.setFont(QFont("Segoe UI", 9))

        separator_y = y_base - 6
        painter.setPen(QPen(QColor(0, 150, 255, 50), 1))
        painter.drawLine(15, separator_y, self._panel_width - 15, separator_y)

        for msg in reversed(self._messages[-8:]):
            level_color = {
                "info": QColor(150, 200, 255, 200),
                "warning": QColor(255, 200, 100, 200),
                "error": QColor(255, 80, 80, 200),
                "success": QColor(100, 255, 150, 200),
            }
            color = level_color.get(msg.level, QColor(200, 200, 200, 200))
            painter.setPen(color)

            lines = self._wrap_text(msg.text, 360)
            for line in lines:
                painter.drawText(15, y_base, line)
                y_base += 15
            y_base += 3

    def _draw_status_bar(self, painter):
        y = self._panel_height - 80
        painter.setPen(QPen(QColor(0, 150, 255, 50), 1))
        painter.drawLine(15, y, self._panel_width - 15, y)

        y += 15
        font = QFont("Consolas", 8)
        painter.setFont(font)
        painter.setPen(QColor(100, 180, 255, 150))

        agents_text = f"Agents: {', '.join(self._active_agents[:3]) if self._active_agents else 'None'}"
        painter.drawText(15, y, agents_text)

        y += 14
        events = self._system_status.get("events", {})
        subs = self._system_status.get("subscribers", 0)
        painter.drawText(15, y, f"Events: {events}  |  Subs: {subs}")

    def _draw_waveform(self, painter):
        y_base = self._panel_height - 30
        painter.setPen(QPen(QColor(0, 180, 255, 100), 1))

        center_y = y_base
        points = len(self._waveform_data)
        for i, val in enumerate(self._waveform_data):
            x = 15 + (i * (self._panel_width - 30) // points)
            h = min(abs(val) * 20, 20)
            painter.drawLine(x, int(center_y - h), x, int(center_y + h))

    def _wrap_text(self, text: str, max_width: int) -> list[str]:
        if not HAS_PYQT6:
            return [text[:60]]
        fm = QFontMetrics(QFont("Consolas", 8))
        words = text.split()
        lines = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip()
            if fm.horizontalAdvance(test) > max_width:
                if current:
                    lines.append(current)
                current = word
            else:
                current = test
        if current:
            lines.append(current)
        return lines if lines else [text[:60]]


_hud_instance = None
_hud_lock = threading.Lock()


def get_hud() -> Optional["HUDOverlay"]:
    global _hud_instance
    with _hud_lock:
        return _hud_instance


def init_hud(app: Optional[QApplication] = None) -> "HUDOverlay":
    global _hud_instance
    if not HAS_PYQT6:
        return None
    with _hud_lock:
        if _hud_instance is None:
            _hud_instance = HUDOverlay()
        return _hud_instance
