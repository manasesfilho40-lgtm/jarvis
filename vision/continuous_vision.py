import asyncio
import hashlib
import logging
import time
from threading import Thread
from typing import Any, Optional

import numpy as np

from core.event_bus import EventType, emit
from vision.screen_analyzer import get_analyzer
from vision.ui_detector import get_detector

logger = logging.getLogger("continuous_vision")


class ContinuousVision:
    def __init__(self, check_interval: float = 2.0, change_threshold: float = 15.0):
        self.check_interval = check_interval
        self.change_threshold = change_threshold
        self._analyzer = None
        self._detector = None
        self._last_screenshot = None
        self._last_hash = ""
        self._last_analysis_time = 0.0
        self._running = False
        self._thread: Optional[Thread] = None
        self._consecutive_same = 0
        self._change_count = 0
        self._total_checks = 0

    def start(self):
        if self._running:
            return
        self._running = True
        self._analyzer = get_analyzer()
        self._detector = get_detector()
        self._thread = Thread(target=self._run_loop, daemon=True, name="ContinuousVision")
        self._thread.start()
        logger.info(f"ContinuousVision started (interval={self.check_interval}s)")

    def stop(self):
        self._running = False
        logger.info("ContinuousVision stopped")

    def _run_loop(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._main_loop())
        except Exception as e:
            logger.error(f"ContinuousVision loop failed: {e}")

    async def _main_loop(self):
        while self._running:
            self._total_checks += 1
            try:
                changed = await self._check_screen()
                if changed:
                    self._change_count += 1
                    analysis = await self._analyze_screen()
                    if analysis:
                        emit(EventType.SCREEN_CHANGE, analysis, source="continuous_vision")

                if self._total_checks % 30 == 0:
                    ui = await self._detect_ui()
                    if ui:
                        emit(EventType.SITUATION_AWARE, ui, source="continuous_vision")

            except Exception as e:
                logger.debug(f"Vision check error: {e}")

            await asyncio.sleep(self.check_interval)

    async def _check_screen(self) -> bool:
        try:
            img = await asyncio.to_thread(self._analyzer.capture)
            if img is None:
                return False

            current_hash = hashlib.md5(img.tobytes()[:10000]).hexdigest()
            if current_hash == self._last_hash:
                self._consecutive_same += 1
                return False

            self._consecutive_same = 0
            self._last_hash = current_hash
            self._last_screenshot = img

            if self._last_analysis_time > 0:
                elapsed = time.time() - self._last_analysis_time
                if elapsed < 5.0:
                    return False

            return True
        except Exception as e:
            logger.debug(f"Screen check error: {e}")
            return False

    async def _analyze_screen(self) -> Optional[dict]:
        self._last_analysis_time = time.time()
        try:
            analysis = await asyncio.to_thread(self._analyzer.analyze, self._last_screenshot)
            return {
                "text_found": bool(analysis.full_text),
                "text_length": len(analysis.full_text),
                "text_preview": analysis.full_text[:300] if analysis.full_text else "",
                "text_blocks": len(analysis.text_blocks),
                "buttons": len(analysis.buttons),
                "ui_elements": len(analysis.ui_elements),
                "resolution": analysis.resolution,
                "timestamp": time.time(),
            }
        except Exception as e:
            logger.debug(f"Screen analysis error: {e}")
            return None

    async def _detect_ui(self) -> Optional[dict]:
        try:
            if self._last_screenshot is None:
                return None
            ui = await asyncio.to_thread(self._detector.analyze, self._last_screenshot)
            return {
                "buttons": len(ui.buttons),
                "text_fields": len(ui.text_fields),
                "images": len(ui.images),
                "videos": len(ui.videos),
                "elements": len(ui.elements),
            }
        except Exception as e:
            return None

    def get_stats(self) -> dict:
        return {
            "total_checks": self._total_checks,
            "changes_detected": self._change_count,
            "running": self._running,
            "interval": self.check_interval,
        }


_continuous_vision_instance = None


def get_continuous_vision(check_interval: float = 2.0) -> ContinuousVision:
    global _continuous_vision_instance
    if _continuous_vision_instance is None:
        _continuous_vision_instance = ContinuousVision(check_interval=check_interval)
    return _continuous_vision_instance
