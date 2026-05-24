import asyncio
import logging
import os
import subprocess
import time
from typing import Any, Optional

from plugins.plugin_base import BasePlugin, HookType, PluginManifest

logger = logging.getLogger("vscode_plugin")

VSCODE_PATHS = [
    r"C:\Users\T-GAMER\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd",
    r"C:\Program Files\Microsoft VS Code\bin\code.cmd",
    "code",
]

manifest = PluginManifest(
    name="vscode",
    version="1.0.0",
    description="Controle do VSCode: abrir arquivos, pastas, executar comandos",
    author="J.A.R.V.I.S",
    priority=50,
    tags=["editor", "code", "vscode"],
)


class VSCodePlugin(BasePlugin):
    def __init__(self, manifest: PluginManifest):
        super().__init__(manifest)
        self._code_path: Optional[str] = None
        self._current_project: Optional[str] = None

    async def on_load(self):
        self._code_path = self._find_code()
        if self._code_path:
            logger.info(f"VSCode found at: {self._code_path}")
        else:
            logger.warning("VSCode not found on system PATH")
        self.register_hook(HookType.ON_MESSAGE, self._handle_vscode_command)

    async def on_unload(self):
        pass

    def _find_code(self) -> Optional[str]:
        for path in VSCODE_PATHS:
            try:
                result = subprocess.run(
                    [path, "--version"], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return path
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        return None

    async def open_file(self, filepath: str) -> str:
        if not self._code_path:
            return "VSCode não encontrado"
        try:
            abs_path = os.path.abspath(filepath)
            subprocess.Popen([self._code_path, abs_path], shell=True)
            return f"Opened {abs_path} in VSCode"
        except Exception as e:
            return f"Error opening file: {e}"

    async def open_folder(self, folder_path: str) -> str:
        if not self._code_path:
            return "VSCode não encontrado"
        try:
            abs_path = os.path.abspath(folder_path)
            subprocess.Popen([self._code_path, abs_path], shell=True)
            self._current_project = abs_path
            return f"Opened folder {abs_path} in VSCode"
        except Exception as e:
            return f"Error opening folder: {e}"

    async def run_command(self, command: str) -> str:
        if not self._code_path:
            return "VSCode não encontrado"
        try:
            subprocess.Popen(
                [self._code_path, "--command", command],
                shell=True,
            )
            return f"Executed VSCode command: {command}"
        except Exception as e:
            return f"Error running command: {e}"

    async def install_extension(self, extension_id: str) -> str:
        if not self._code_path:
            return "VSCode não encontrado"
        try:
            result = subprocess.run(
                [self._code_path, "--install-extension", extension_id],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                return f"Installed extension: {extension_id}"
            return f"Failed: {result.stderr[:200]}"
        except Exception as e:
            return f"Error: {e}"

    async def get_open_projects(self) -> list[str]:
        projects = []
        if self._current_project:
            projects.append(self._current_project)
        try:
            result = subprocess.run(
                "tasklist /FI \"IMAGENAME eq Code.exe\" /NH",
                capture_output=True, text=True, shell=True, timeout=5,
            )
            if "Code.exe" in result.stdout:
                logger.info("VSCode is running")
        except Exception:
            pass
        return projects

    async def _handle_vscode_command(self, event_type, data, source):
        text = data if isinstance(data, str) else (data.get("text", "") if isinstance(data, dict) else "")
        text_lower = text.lower()
        if "vscode" not in text_lower and "code" not in text_lower:
            return None
        return {"plugin": "vscode", "handled": True}
