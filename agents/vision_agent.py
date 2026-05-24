import asyncio
import logging
from typing import Any, Optional

import numpy as np

from agents.agent_base import BaseAgent
from core.event_bus import EventType, emit
from core.runtime import get_runtime
from vision.screen_analyzer import ScreenAnalyzer, get_analyzer
from vision.ui_detector import UIDetector, get_detector

logger = logging.getLogger("vision_agent")


class VisionAgent(BaseAgent):
    def __init__(self, analyze_interval: float = 10.0):
        super().__init__("vision", "Screen analysis, OCR, UI detection, and visual understanding")
        self.analyze_interval = analyze_interval
        self._analyzer: Optional[ScreenAnalyzer] = None
        self._detector: Optional[UIDetector] = None
        self._last_analysis_time = 0.0
        self._last_screen_hash = ""

    async def think(self, context: dict) -> Optional[dict]:
        now = asyncio.get_event_loop().time()
        if now - self._last_analysis_time < self.analyze_interval:
            return None

        self._last_analysis_time = now

        try:
            if self._analyzer is None:
                self._analyzer = get_analyzer()
            if self._detector is None:
                self._detector = get_detector()

            image = await asyncio.to_thread(self._analyzer.capture)
            if image is None:
                return {"action": "capture_failed"}

            screen_hash = hash(image.tobytes()[:1000])
            if screen_hash == self._last_screen_hash:
                return None
            self._last_screen_hash = screen_hash

            analysis = await asyncio.to_thread(self._analyzer.analyze, image)
            ui_analysis = await asyncio.to_thread(self._detector.analyze, image)

            self._runtime.update_system(screen_resolution=analysis.resolution)

            if analysis.full_text:
                emit(EventType.OCR_RESULT, {
                    "text": analysis.full_text[:500],
                    "blocks": len(analysis.text_blocks),
                }, source=self.name)

            if ui_analysis.buttons:
                emit(EventType.UI_ELEMENT_DETECTED, {
                    "buttons": len(ui_analysis.buttons),
                    "text_fields": len(ui_analysis.text_fields),
                    "total_elements": len(ui_analysis.elements),
                }, source=self.name)

            return {
                "action": "analyze",
                "text_found": bool(analysis.full_text),
                "text_length": len(analysis.full_text),
                "ui_elements": len(ui_analysis.elements),
                "buttons": len(ui_analysis.buttons),
                "text_fields": len(ui_analysis.text_fields),
                "resolution": analysis.resolution,
            }

        except Exception as e:
            logger.error(f"Vision analysis failed: {e}")
            return {"action": "error", "error": str(e)}

    async def act(self, thought: dict) -> Any:
        return thought

    async def observe(self, event) -> Optional[dict]:
        return None

    def analyze_screen(self) -> str:
        if self._analyzer is None:
            self._analyzer = get_analyzer()
        return self._analyzer.get_screen_context()

    def find_text(self, text: str) -> Optional[tuple[int, int]]:
        if self._analyzer is None:
            self._analyzer = get_analyzer()
        return self._analyzer.find_and_click_text(text)

    def screenshot(self, path: str = "") -> str:
        if self._analyzer is None:
            self._analyzer = get_analyzer()
        return self._analyzer.save_screenshot(path)

    def subscribe_to_events(self):
        self.subscribe_to(
            EventType.SCREEN_CHANGE,
            EventType.USER_INPUT,
        )


_vision_agent_instance = None


def get_vision_agent() -> VisionAgent:
    global _vision_agent_instance
    if _vision_agent_instance is None:
        _vision_agent_instance = VisionAgent()
    return _vision_agent_instance
