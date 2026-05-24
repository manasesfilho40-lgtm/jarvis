import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger("screen_analyzer")


try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    logger.warning("OpenCV not installed. Install with: pip install opencv-python")


try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False
    logger.warning("pytesseract not installed. Install with: pip install pytesseract")


try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


@dataclass
class DetectionResult:
    label: str
    confidence: float
    bounds: tuple[int, int, int, int]
    center: tuple[int, int] = (0, 0)
    text: str = ""

    def __post_init__(self):
        x, y, w, h = self.bounds
        self.center = (x + w // 2, y + h // 2)


@dataclass
class ScreenAnalysis:
    text_blocks: list[dict] = field(default_factory=list)
    ui_elements: list[DetectionResult] = field(default_factory=list)
    buttons: list[DetectionResult] = field(default_factory=list)
    text_fields: list[DetectionResult] = field(default_factory=list)
    images: list[DetectionResult] = field(default_factory=list)
    full_text: str = ""
    resolution: tuple[int, int] = (0, 0)
    capture_time: float = 0.0
    analysis_time_ms: float = 0.0


class ScreenAnalyzer:
    def __init__(self, tesseract_path: str = "", ocr_lang: str = "por+eng"):
        self.ocr_lang = ocr_lang
        self._last_screenshot: Optional[np.ndarray] = None
        self._last_analysis: Optional[ScreenAnalysis] = None

        if HAS_TESSERACT and tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path

    def capture(self, monitor: int = 1) -> Optional[np.ndarray]:
        try:
            import mss
            with mss.mss() as sct:
                monitors = sct.monitors
                if monitor < len(monitors):
                    img = sct.grab(monitors[monitor])
                else:
                    img = sct.grab(monitors[1])
                arr = np.array(img)
                self._last_screenshot = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR) if HAS_CV2 else arr
                return self._last_screenshot
        except Exception as e:
            logger.error(f"Capture failed: {e}")
            return None

    def capture_region(self, x: int, y: int, width: int, height: int) -> Optional[np.ndarray]:
        try:
            import mss
            with mss.mss() as sct:
                monitor = {"top": y, "left": x, "width": width, "height": height}
                img = sct.grab(monitor)
                arr = np.array(img)
                return cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR) if HAS_CV2 else arr
        except Exception as e:
            logger.error(f"Region capture failed: {e}")
            return None

    def analyze(self, image: Optional[np.ndarray] = None) -> ScreenAnalysis:
        start = time.time()
        img = image if image is not None else self._last_screenshot
        if img is None:
            img = self.capture()
        if img is None:
            return ScreenAnalysis()

        analysis = ScreenAnalysis(
            resolution=(img.shape[1], img.shape[0]),
            capture_time=time.time(),
        )

        if HAS_CV2:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

            ocr_text = self._perform_ocr(img, gray)
            analysis.full_text = ocr_text
            analysis.text_blocks = self._extract_text_blocks(gray)

            analysis.buttons = self._detect_buttons(gray, img)
            analysis.ui_elements = self._detect_ui_elements(gray, img)

        analysis.analysis_time_ms = (time.time() - start) * 1000
        self._last_analysis = analysis
        return analysis

    def _perform_ocr(self, img: np.ndarray, gray: np.ndarray) -> str:
        if not HAS_TESSERACT:
            return "[OCR: pytesseract not installed]"
        try:
            text = pytesseract.image_to_string(gray, lang=self.ocr_lang)
            return text.strip()
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            return ""

    def _extract_text_blocks(self, gray: np.ndarray) -> list[dict]:
        blocks = []
        if not HAS_TESSERACT:
            return blocks
        try:
            data = pytesseract.image_to_data(gray, lang=self.ocr_lang, output_type=pytesseract.Output.DICT)
            for i in range(len(data["text"])):
                text = data["text"][i].strip()
                if text and int(data["conf"][i]) > 30:
                    blocks.append({
                        "text": text,
                        "confidence": int(data["conf"][i]),
                        "x": data["left"][i],
                        "y": data["top"][i],
                        "w": data["width"][i],
                        "h": data["height"][i],
                    })
        except Exception as e:
            logger.error(f"Text block extraction failed: {e}")
        return blocks

    def _detect_buttons(self, gray: np.ndarray, color: np.ndarray) -> list[DetectionResult]:
        buttons = []
        if not HAS_CV2:
            return buttons
        try:
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 50, 150)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                area = w * h
                if 500 < area < 50000 and 0.5 < w / h < 5:
                    buttons.append(DetectionResult(
                        label="button",
                        confidence=0.5,
                        bounds=(x, y, w, h),
                    ))
        except Exception as e:
            logger.error(f"Button detection failed: {e}")
        return buttons

    def _detect_ui_elements(self, gray: np.ndarray, color: np.ndarray) -> list[DetectionResult]:
        elements = []
        if not HAS_CV2:
            return elements
        try:
            thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                           cv2.THRESH_BINARY_INV, 11, 2)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                area = w * h
                if 100 < area < 100000:
                    elements.append(DetectionResult(
                        label="ui_element",
                        confidence=0.4,
                        bounds=(x, y, w, h),
                    ))
        except Exception as e:
            logger.error(f"UI element detection failed: {e}")
        return elements

    def find_text_on_screen(self, target: str, image: Optional[np.ndarray] = None) -> list[dict]:
        analysis = self.analyze(image)
        target_lower = target.lower()
        return [b for b in analysis.text_blocks if target_lower in b["text"].lower()]

    def find_and_click_text(self, target: str) -> Optional[tuple[int, int]]:
        matches = self.find_text_on_screen(target)
        if not matches:
            return None

        match = matches[0]
        cx = match["x"] + match["w"] // 2
        cy = match["y"] + match["h"] // 2

        try:
            import pyautogui
            pyautogui.click(cx, cy)
            logger.info(f"Clicked '{target}' at ({cx}, {cy})")
            return (cx, cy)
        except Exception as e:
            logger.error(f"Click failed: {e}")
            return None

    def get_text_at_region(self, x: int, y: int, w: int, h: int) -> str:
        img = self.capture_region(x, y, w, h)
        if img is None:
            return ""
        if not HAS_CV2:
            return "[OpenCV not available]"
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return self._perform_ocr(img, gray)

    def detect_changes(self, interval: float = 1.0) -> bool:
        img1 = self.capture()
        if img1 is None:
            return False
        time.sleep(interval)
        img2 = self.capture()
        if img2 is None:
            return False

        if HAS_CV2:
            diff = cv2.absdiff(img1, img2)
            mean_diff = np.mean(diff)
            return mean_diff > 10
        return False

    def get_screen_context(self) -> str:
        analysis = self.analyze()
        if not analysis.full_text:
            return "No text detected on screen."

        lines = analysis.full_text.split("\n")
        lines = [l.strip() for l in lines if l.strip()]
        text_preview = "\n".join(lines[:30])

        summary = (
            f"Screen: {analysis.resolution[0]}x{analysis.resolution[1]}\n"
            f"Text blocks: {len(analysis.text_blocks)}\n"
            f"Buttons: {len(analysis.buttons)}\n"
            f"UI elements: {len(analysis.ui_elements)}\n"
            f"Text detected:\n{text_preview[:2000]}"
        )
        return summary

    def save_screenshot(self, path: str = "") -> str:
        img = self.capture()
        if img is None:
            return ""
        if not path:
            path = str(Path.home() / "Desktop" / f"screenshot_{int(time.time())}.png")
        if HAS_CV2:
            cv2.imwrite(path, img)
        else:
            from PIL import Image
            Image.fromarray(img).save(path)
        return path

    def __repr__(self):
        return f"ScreenAnalyzer(ocr={HAS_TESSERACT}, cv={HAS_CV2})"


_analyzer_instance = None


def get_analyzer(tesseract_path: str = "") -> ScreenAnalyzer:
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = ScreenAnalyzer(tesseract_path=tesseract_path)
    return _analyzer_instance
