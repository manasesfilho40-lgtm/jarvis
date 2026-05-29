# -*- coding: utf-8 -*-
"""
JARVIS MARK XXXIX - Neural WebGL Interface Wrapper
Integrates Three.js 3D Spiky Sphere with PyQt6 WebEngineView
"""
import sys
import os
import json
from PyQt6.QtCore import QUrl, pyqtSignal, QObject, QFileSystemWatcher
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage

from core.utils import global_command_queue as _global_command_queue
try:
    from web_server import _push_log, _push_state, _push_model_info as _ws_push
except ImportError:
    _push_log = _push_state = _ws_push = None

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
        self.app.exec()

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
    leads_signal = pyqtSignal(str)
    geopolitics_signal = pyqtSignal(str)
    quota_signal = pyqtSignal(str)

    def __init__(self):
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
        
        # Setup filesystem watcher for leads database
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._on_leads_file_changed)
        self.watcher.directoryChanged.connect(self._on_leads_dir_changed)
        
        self.leads_db_paths = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), "config", "leads_db.json")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "memory", "leads_db.json")),
        ]
        
        for path in self.leads_db_paths:
            parent_dir = os.path.dirname(path)
            if os.path.exists(parent_dir):
                self.watcher.addPath(parent_dir)
            if os.path.exists(path):
                self.watcher.addPath(path)

        # Connect safe slots
        self.log_signal.connect(self._safe_write_log)
        self.state_signal.connect(self._safe_set_state)
        self.volume_signal.connect(self._safe_set_volume)
        self.leads_signal.connect(self._safe_update_leads)
        self.geopolitics_signal.connect(self._safe_update_geopolitics)
        self.quota_signal.connect(self._safe_update_quota)
        
        # Load local HTML
        html_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "jarvis_ui.html"))
        self.web_view.load(QUrl.fromLocalFile(html_path))
        
        # Center window on screen
        from PyQt6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen().availableGeometry()
        win_geo = self.root_win.frameGeometry()
        win_geo.moveCenter(screen.center())
        self.root_win.move(win_geo.topLeft())

        # Display window
        self.root_win.show()
        self.root_win.raise_()
        self.root_win.activateWindow()

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

        # Sync model info
        self._push_model_info()

        # Load initial leads from any existing database file
        for db_path in self.leads_db_paths:
            if os.path.exists(db_path):
                self._reload_leads_file(db_path)
                break

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
            elif cmd.startswith("set_mode:"):
                mode = cmd.split(":", 1)[1]
                from agent.local_genai import set_routing_mode
                set_routing_mode(mode)
                mode_names = {"gemini": "Gemini (Nuvem)", "llama": "Ollama (Local)", "auto": "Automático"}
                self.write_log(f"SYS: Modo alterado para {mode_names.get(mode, mode)}")
                self._push_model_info()
            elif cmd.startswith("set_ollama_model:"):
                model_name = cmd.split(":", 1)[1]
                from agent.local_genai import set_ollama_model
                set_ollama_model(model_name)
                self.write_log(f"SYS: Modelo Ollama alterado para {model_name}")
                self._push_model_info()
            else:
                if cmd == "start whatsapp automation agent":
                    cmd = "open whatsapp automation agent"
                # Dispatch command back to python brain listener (Gemini Live/Llama)
                if self.on_text_command:
                    self.on_text_command(cmd)

    def wait_for_api_key(self):
        from core.utils import BASE_DIR
        import json
        config_path = BASE_DIR / "config" / "api_keys.json"
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                key = json.load(f).get("gemini_api_key", "")
            if not key or key == "YOUR_GEMINI_API_KEY":
                print("[JARVIS] API key nao configurada. Use o campo de texto para inserir sua chave Gemini.")
                self.write_log("SYS: Insira sua chave Gemini no campo de texto para configurar.")
        except Exception as e:
            print(f"[JARVIS] Nao foi possivel ler api_keys.json: {e}")

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
        
    def update_leads(self, leads_json_str):
        self.leads_signal.emit(leads_json_str)

    def update_geopolitics(self, geopolitics_json_str):
        self.geopolitics_signal.emit(geopolitics_json_str)

    def _safe_write_log(self, is_user, clean_msg):
        if not self._page_loaded:
            self._log_buffer.append((is_user, clean_msg))
        else:
            js_code = f"addLog({str(is_user).lower()}, {json.dumps(clean_msg)});"
            self.web_view.page().runJavaScript(js_code)
        if _push_log:
            try:
                _push_log(is_user, clean_msg)
            except Exception:
                pass

    def _safe_set_state(self, state):
        self._current_state = state
        if self._page_loaded:
            js_code = f"updateState({json.dumps(state)});"
            self.web_view.page().runJavaScript(js_code)
        if _push_state:
            try:
                _push_state(state)
            except Exception:
                pass

    def _safe_set_volume(self, vol):
        self._current_volume = vol
        if self._page_loaded:
            js_code = f"updateVolume({vol});"
            self.web_view.page().runJavaScript(js_code)
            
    def _safe_update_leads(self, leads_json_str):
        if self._page_loaded:
            js_code = f"updateLeadsData({json.dumps(leads_json_str)});"
            self.web_view.page().runJavaScript(js_code)

    def _safe_update_geopolitics(self, geopolitics_json_str):
        if self._page_loaded:
            js_code = f"updateGeopoliticsNews({json.dumps(geopolitics_json_str)});"
            self.web_view.page().runJavaScript(js_code)

    def _push_model_info(self):
        from agent.local_genai import get_current_model_info
        info = get_current_model_info()
        info_json = json.dumps(info)
        if self._page_loaded:
            js_code = f"updateModelInfo({info_json});"
            self.web_view.page().runJavaScript(js_code)
        if _ws_push:
            try:
                _ws_push(info_json)
            except Exception:
                pass

    def update_quota(self, quota_json_str):
        self.quota_signal.emit(quota_json_str)

    def _safe_update_quota(self, quota_json_str):
        if self._page_loaded:
            js_code = f"updateApiQuota({quota_json_str});"
            self.web_view.page().runJavaScript(js_code)

    def _reload_leads_file(self, path):
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    # Validate JSON structure
                    json.loads(content)
                    self.update_leads(content)
        except Exception as e:
            print(f"[JARVIS UI LEADS WATCHER ERROR] {e}")

    def _on_leads_file_changed(self, path):
        if os.path.basename(path) == "leads_db.json":
            self._reload_leads_file(path)

    def _on_leads_dir_changed(self, path):
        for db_path in self.leads_db_paths:
            if os.path.exists(db_path) and db_path not in self.watcher.files():
                self.watcher.addPath(db_path)
                self._reload_leads_file(db_path)

    def show(self):
        self.root_win.show()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    ui = JarvisUI()
    sys.exit(app.exec())
