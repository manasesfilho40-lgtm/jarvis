# -*- coding: utf-8 -*-
"""
JARVIS MARK XXXIX - Neural WebGL Interface Wrapper
Integrates Three.js 3D Spiky Sphere with PyQt6 WebEngineView
"""
import sys
import os
import json
from PyQt6.QtCore import Qt, QUrl, QTimer, pyqtSignal, QObject
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtGui import QIcon

class RootWrapper(QObject):
    def __init__(self, window, app):
        super().__init__()
        self.window = window
        self.app = app

    def deiconify(self):
        self.window.showNormal()
        self.window.activateWindow()
        self.window.raise_()

    def lift(self):
        self.window.raise_()

    def focus_force(self):
        self.window.activateWindow()
        self.window.raise_()

    def mainloop(self):
        sys.exit(self.app.exec())

class JarvisWebPage(QWebEnginePage):
    def __init__(self, parent, console_callback):
        super().__init__(parent)
        self.console_callback = console_callback

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        self.console_callback(level, message, lineNumber, sourceID)

class JarvisUI(QObject):
    log_signal = pyqtSignal(bool, str)
    state_signal = pyqtSignal(str)
    volume_signal = pyqtSignal(float)

    def __init__(self, face_image_path=None):
        super().__init__()
        self.app = QApplication.instance() or QApplication(sys.argv)
        
        # Main window setup
        self.root_win = QMainWindow()
        self.root_win.setWindowTitle("JARVIS \u00B7 MARK XXXIX")
        self.root_win.resize(1024, 768)
        self.root_win.setStyleSheet("background-color: #000000;")
        
        # API Compatibility properties
        self.root = RootWrapper(self.root_win, self.app)
        self.muted = False
        self.current_file = None
        self.on_text_command = None
        self._current_state = "LISTENING"
        self._current_volume = 0.0
        
        # Buffering for logs prior to page load completion
        self._page_loaded = False
        self._log_buffer = []
        
        # Create QWebEngineView with custom page to intercept JavaScript logs
        self.web_view = QWebEngineView(self.root_win)
        self.web_page = JarvisWebPage(self.web_view, self._on_console_message)
        self.web_view.setPage(self.web_page)
        self.root_win.setCentralWidget(self.web_view)
        
        # Configure settings for WebGL
        settings = self.web_view.settings()
        settings.setAttribute(settings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(settings.WebAttribute.Accelerated2dCanvasEnabled, True)
        settings.setAttribute(settings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(settings.WebAttribute.LocalContentCanAccessFileUrls, True)
        
        # Connect page load finished signal
        self.web_view.loadFinished.connect(self._on_load_finished)
        
        # Connect safe slots
        self.log_signal.connect(self._safe_write_log)
        self.state_signal.connect(self._safe_set_state)
        self.volume_signal.connect(self._safe_set_volume)
        
        # Load local HTML
        html_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "jarvis_ui.html"))
        self.web_view.load(QUrl.fromLocalFile(html_path))
        
        # Display window
        self.root_win.show()
        self.root_win.raise_()

    def _on_load_finished(self, ok):
        self._page_loaded = True
        
        # Sync and print initial logs
        for is_user, msg in self._log_buffer:
            js_code = f"addLog({str(is_user).lower()}, {json.dumps(msg)});"
            self.web_view.page().runJavaScript(js_code)
        self._log_buffer.clear()
        
        # Sync initial state
        state_js = f"updateState({json.dumps(self._current_state)});"
        self.web_view.page().runJavaScript(state_js)
        
        # Sync initial volume
        vol_js = f"updateVolume({self._current_volume});"
        self.web_view.page().runJavaScript(vol_js)

    def _on_console_message(self, level, message, line, source_id):
        # Listen for console.log statements from JS beginning with "CMD:"
        if message.startswith("CMD:"):
            cmd = message[4:]
            if cmd == "speak_trigger":
                # Toggle mic/speak state internally
                self.muted = not self.muted
                state = "MUTED" if self.muted else "LISTENING"
                self.set_state(state)
                # Log status change in visual chat container
                log_msg = "SYS: Microfone silenciado." if self.muted else "SYS: Microfone ativado."
                self.write_log(log_msg)
            else:
                # Dispatch command back to python brain listener (Gemini Live/Llama)
                if self.on_text_command:
                    self.on_text_command(cmd)

    def wait_for_api_key(self):
        pass

    def write_log(self, text):
        is_user = False
        clean_msg = text
        
        upper_text = text.upper()
        if upper_text.startswith("YOU:"):
            is_user = True
            clean_msg = text[4:].strip()
        elif upper_text.startswith("YOU "):
            is_user = True
            clean_msg = text[4:].strip()
        elif upper_text.startswith("VOC\u00CA:"):
            is_user = True
            clean_msg = text[5:].strip()
        elif upper_text.startswith("VOC\u00CA "):
            is_user = True
            clean_msg = text[5:].strip()
        elif upper_text.startswith("JARVIS:"):
            is_user = False
            clean_msg = text[7:].strip()
        elif upper_text.startswith("JARVIS "):
            is_user = False
            clean_msg = text[7:].strip()
        elif upper_text.startswith("SYS:"):
            is_user = False
            clean_msg = text[4:].strip()
        elif upper_text.startswith("ERR:"):
            is_user = False
            clean_msg = text[4:].strip()
            
        print(f"[JARVIS UI LOG] {text}")
        self.log_signal.emit(is_user, clean_msg)

    def set_state(self, state):
        self.state_signal.emit(state)

    def set_volume(self, vol):
        self.volume_signal.emit(vol)

    def _safe_write_log(self, is_user, clean_msg):
        if not self._page_loaded:
            self._log_buffer.append((is_user, clean_msg))
        else:
            js_code = f"addLog({str(is_user).lower()}, {json.dumps(clean_msg)});"
            self.web_view.page().runJavaScript(js_code)

    def _safe_set_state(self, state):
        self._current_state = state
        if self._page_loaded:
            js_code = f"updateState({json.dumps(state)});"
            self.web_view.page().runJavaScript(js_code)

    def _safe_set_volume(self, vol):
        self._current_volume = vol
        if self._page_loaded:
            js_code = f"updateVolume({vol});"
            self.web_view.page().runJavaScript(js_code)

    def show(self):
        self.root_win.show()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    ui = JarvisUI()
    sys.exit(app.exec())
