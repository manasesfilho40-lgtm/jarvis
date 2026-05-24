import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

logger = logging.getLogger("ui_detector")


try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False


@dataclass
class UIElement:
    element_type: str
    text: str = ""
    bounds: tuple[int, int, int, int] = (0, 0, 0, 0)
    center: tuple[int, int] = (0, 0)
    confidence: float = 0.0
    attributes: dict = field(default_factory=dict)

    @property
    def x(self):
        return self.bounds[0]

    @property
    def y(self):
        return self.bounds[1]

    @property
    def w(self):
        return self.bounds[2]

    @property
    def h(self):
        return self.bounds[3]

    @property
    def area(self):
        return self.w * self.h

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x <= self.x + self.w and self.y <= y <= self.y + self.h


@dataclass
class UIAnalysis:
    elements: list[UIElement] = field(default_factory=list)
    buttons: list[UIElement] = field(default_factory=list)
    text_fields: list[UIElement] = field(default_factory=list)
    labels: list[UIElement] = field(default_factory=list)
    checkboxes: list[UIElement] = field(default_factory=list)
    dropdowns: list[UIElement] = field(default_factory=list)
    images: list[UIElement] = field(default_factory=list)
    icons: list[UIElement] = field(default_factory=list)
    windows: list[UIElement] = field(default_factory=list)
    taskbar: Optional[UIElement] = None
    analysis_time_ms: float = 0.0


class UIDetector:
    def __init__(self):
        self._button_patterns = [
            r'\b(ok|cancel|save|delete|submit|confirm|close|exit|back|next|'
            r'login|sign|register|search|send|upload|download|edit|'
            r'apply|reset|retry|continue|start|stop|pause|play|'
            r'entrar|cancelar|salvar|deletar|enviar|buscar|'
            r'procurar|voltar|pr[oó]ximo|anterior|confirmar|'
            r'fechar|aplicar|cadastrar|ok)\b'
        ]
        self._compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self._button_patterns]

    def analyze(self, image: np.ndarray) -> UIAnalysis:
        start = time.time()
        analysis = UIAnalysis()

        if not HAS_CV2:
            analysis.analysis_time_ms = (time.time() - start) * 1000
            return analysis

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        height, width = gray.shape

        analysis.windows = self._detect_windows(gray)
        analysis.taskbar = self._detect_taskbar(gray, height, width)
        analysis.buttons = self._detect_interactive_elements(gray)
        analysis.text_fields = self._detect_text_fields(gray)
        analysis.checkboxes = self._detect_checkboxes(gray)
        analysis.icons = self._detect_icons(gray)
        analysis.labels = self._detect_labels(image)

        all_elements = (
            analysis.buttons + analysis.text_fields + analysis.checkboxes +
            analysis.dropdowns + analysis.icons + analysis.labels
        )
        analysis.elements = self._deduplicate(all_elements)
        analysis.analysis_time_ms = (time.time() - start) * 1000
        return analysis

    def _detect_windows(self, gray: np.ndarray) -> list[UIElement]:
        windows = []
        try:
            _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                area = w * h
                if area > 50000 and w > 200 and h > 100:
                    windows.append(UIElement(
                        element_type="window",
                        bounds=(x, y, w, h),
                        confidence=0.6,
                    ))
        except Exception as e:
            logger.error(f"Window detection failed: {e}")
        return windows

    def _detect_taskbar(self, gray: np.ndarray, height: int, width: int) -> Optional[UIElement]:
        bottom_region = gray[height - 60:height, :]
        try:
            edges = cv2.Canny(bottom_region, 50, 150)
            if np.mean(edges) > 5:
                return UIElement(
                    element_type="taskbar",
                    bounds=(0, height - 60, width, 60),
                    confidence=0.7,
                )
        except Exception as e:
            logger.error(f"Taskbar detection failed: {e}")
        return None

    def _detect_interactive_elements(self, gray: np.ndarray) -> list[UIElement]:
        elements = []
        try:
            blurred = cv2.GaussianBlur(gray, (3, 3), 0)
            edges = cv2.Canny(blurred, 30, 100)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                area = w * h
                aspect = w / h if h > 0 else 0

                if 200 < area < 30000 and 0.8 < aspect < 5.0:
                    elements.append(UIElement(
                        element_type="interactive",
                        bounds=(x, y, w, h),
                        confidence=0.5,
                    ))
        except Exception as e:
            logger.error(f"Interactive element detection failed: {e}")
        return elements

    def _detect_text_fields(self, gray: np.ndarray) -> list[UIElement]:
        fields = []
        try:
            thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                           cv2.THRESH_BINARY_INV, 11, 2)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 5))
            morph = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
            contours, _ = cv2.findContours(morph, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                aspect = w / h if h > 0 else 0
                if aspect > 3 and w > 50 and h > 10 and h < 80:
                    fields.append(UIElement(
                        element_type="text_field",
                        bounds=(x, y, w, h),
                        confidence=0.6,
                    ))
        except Exception as e:
            logger.error(f"Text field detection failed: {e}")
        return fields

    def _detect_checkboxes(self, gray: np.ndarray) -> list[UIElement]:
        boxes = []
        try:
            edges = cv2.Canny(gray, 50, 150)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                area = w * h
                aspect = w / h if h > 0 else 0

                if 50 < area < 2000 and 0.8 < aspect < 1.2 and cv2.contourArea(cnt) > 0:
                    perimeter = cv2.arcLength(cnt, True)
                    if perimeter > 0:
                        circularity = 4 * np.pi * cv2.contourArea(cnt) / (perimeter * perimeter)
                        if circularity > 0.7:
                            boxes.append(UIElement(
                                element_type="checkbox",
                                bounds=(x, y, w, h),
                                confidence=0.5,
                            ))
        except Exception as e:
            logger.error(f"Checkbox detection failed: {e}")
        return boxes

    def _detect_icons(self, gray: np.ndarray) -> list[UIElement]:
        icons = []
        try:
            small = cv2.resize(gray, (0, 0), fx=0.5, fy=0.5)
            edges = cv2.Canny(small, 30, 100)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                x, y, w, h = x * 2, y * 2, w * 2, h * 2
                area = w * h
                if 100 < area < 10000 and 0.5 < w / h < 2.0:
                    icons.append(UIElement(
                        element_type="icon",
                        bounds=(x, y, w, h),
                        confidence=0.4,
                    ))
        except Exception as e:
            logger.error(f"Icon detection failed: {e}")
        return icons

    def _detect_labels(self, image: np.ndarray) -> list[UIElement]:
        labels = []
        if not HAS_TESSERACT:
            return labels
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
            data = pytesseract.image_to_data(gray, lang="por+eng", output_type=pytesseract.Output.DICT)

            for i in range(len(data["text"])):
                text = data["text"][i].strip()
                if text and int(data["conf"][i]) > 40:
                    is_button = any(p.search(text) for p in self._compiled_patterns)
                    labels.append(UIElement(
                        element_type="button" if is_button else "label",
                        text=text,
                        bounds=(
                            data["left"][i],
                            data["top"][i],
                            data["width"][i],
                            data["height"][i],
                        ),
                        confidence=int(data["conf"][i]) / 100.0,
                    ))
        except Exception as e:
            logger.error(f"Label detection failed: {e}")
        return labels

    def _deduplicate(self, elements: list[UIElement]) -> list[UIElement]:
        if not elements:
            return []
        sorted_el = sorted(elements, key=lambda e: (e.confidence, e.area), reverse=True)
        unique = []
        for el in sorted_el:
            if not any(u.bounds == el.bounds for u in unique):
                unique.append(el)
        return unique

    def find_element_by_text(self, text: str, analysis: UIAnalysis) -> Optional[UIElement]:
        text_lower = text.lower()
        for el in analysis.elements:
            if text_lower in el.text.lower():
                return el
        return None

    def find_elements_by_type(self, element_type: str, analysis: UIAnalysis) -> list[UIElement]:
        return [el for el in analysis.elements if el.element_type == element_type]

    def get_interactive_context(self, analysis: UIAnalysis) -> str:
        lines = []
        for el in analysis.elements[:20]:
            if el.text:
                lines.append(f"  [{el.element_type}] '{el.text}' at ({el.x},{el.y}) {el.w}x{el.h}")
        return "\n".join(lines)


_detector_instance = None


def get_detector() -> UIDetector:
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = UIDetector()
    return _detector_instance
