import asyncio
import json
import logging
import os
import subprocess
import threading
import time
from typing import Any, Optional

from plugins.plugin_base import BasePlugin, HookType, PluginManifest

logger = logging.getLogger("spotify_plugin")

manifest = PluginManifest(
    name="spotify",
    version="1.0.0",
    description="Controle do Spotify: play, pause, next, search, volume",
    author="J.A.R.V.I.S",
    priority=60,
    tags=["music", "spotify", "media"],
)


class SpotifyPlugin(BasePlugin):
    def __init__(self, manifest: PluginManifest):
        super().__init__(manifest)
        self._spotify_path = self._find_spotify()
        self._current_track: Optional[str] = None
        self._is_playing = False

    async def on_load(self):
        logger.info("Spotify plugin loaded")
        self.register_hook(HookType.ON_EVENT, self._on_event)

    async def on_unload(self):
        pass

    def _find_spotify(self) -> Optional[str]:
        candidates = [
            os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe"),
            r"C:\Users\T-GAMER\AppData\Roaming\Spotify\Spotify.exe",
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return None

    def _spotify_cmd(self, cmd: str) -> Optional[str]:
        try:
            result = subprocess.run(
                ["powershell", "-Command", f"""
$wshell = New-Object -ComObject wscript.shell
$wshell.SendKeys('{cmd}')
"""],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip()
        except Exception as e:
            logger.warning(f"Spotify sendkeys failed: {e}")
            return None

    async def play_pause(self) -> str:
        self._spotify_cmd("{SPACE}")
        self._is_playing = not self._is_playing
        return "Play/Pause toggled"

    async def next_track(self) -> str:
        self._spotify_cmd("^{RIGHT}")
        self._current_track = None
        return "Next track"

    async def previous_track(self) -> str:
        self._spotify_cmd("^{LEFT}")
        self._current_track = None
        return "Previous track"

    async def volume_up(self) -> str:
        self._spotify_cmd("^{UP}")
        return "Volume up"

    async def volume_down(self) -> str:
        self._spotify_cmd("^{DOWN}")
        return "Volume down"

    async def mute(self) -> str:
        self._spotify_cmd("^{DOWN}")
        return "Muted"

    async def is_running(self) -> bool:
        try:
            result = subprocess.run(
                "tasklist /FI \"IMAGENAME eq Spotify.exe\" /NH",
                capture_output=True, text=True, shell=True, timeout=5,
            )
            return "Spotify.exe" in result.stdout
        except Exception:
            return False

    async def launch(self) -> str:
        if self._spotify_path and os.path.exists(self._spotify_path):
            subprocess.Popen([self._spotify_path], shell=True)
            return "Spotify launched"
        return "Spotify not found"

    async def get_now_playing(self) -> str:
        if not await self.is_running():
            return "Spotify is not running"
        try:
            result = subprocess.run(
                ["powershell", "-Command", """
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Foreground {
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder text, int count);
}
"@
$h = [Foreground]::GetForegroundWindow()
$sb = New-Object System.Text.StringBuilder 256
[Foreground]::GetWindowText($h, $sb, 256)
$sb.ToString()
"""],
                capture_output=True, text=True, timeout=5,
            )
            title = result.stdout.strip()
            if "Spotify" in title:
                self._current_track = title.replace(" - Spotify", "").strip()
                return self._current_track or "Unknown track"
            return "Spotify window not focused"
        except Exception as e:
            return f"Error: {e}"

    async def _on_event(self, event_type: str, data: dict, source: str):
        text = data.get("message", "") if isinstance(data, dict) else str(data)
        text_lower = text.lower()
        if "spotify" not in text_lower and "música" not in text_lower and "music" not in text_lower:
            return None

        if "tocar" in text_lower or "play" in text_lower:
            return await self.play_pause()
        if "próxima" in text_lower or "next" in text_lower or "pular" in text_lower:
            return await self.next_track()
        if "voltar" in text_lower or "previous" in text_lower:
            return await self.previous_track()
        if "volume" in text_lower:
            return "Use: aumentar volume / diminuir volume"
        return None
