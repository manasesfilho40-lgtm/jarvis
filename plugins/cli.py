import asyncio
import json
import logging
import shlex
from typing import Any, Optional

from plugins.plugin_base import BasePlugin, PluginManifest, HookType

logger = logging.getLogger("plugin_cli")


class CLIPlugin(BasePlugin):
    def __init__(self, manifest: Optional[PluginManifest] = None):
        if manifest is None:
            manifest = PluginManifest(
                name="cli",
                version="1.0.0",
                description="CLI interface - command history, tab completion, color output",
            )
        super().__init__(manifest)
        self._history: list[str] = []
        self._max_history: int = 100
        self._prompt: str = "J.A.R.V.I.S> "

    async def on_load(self):
        self._max_history = int(self.config.get("max_history", 100))
        self._prompt = self.config.get("prompt", "J.A.R.V.I.S> ")
        logger.info("CLI plugin loaded")

    async def on_unload(self):
        logger.info("CLI plugin unloaded")

    async def format_output(self, data: Any, format_type: str = "auto") -> str:
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            lines = []
            for key, value in data.items():
                if isinstance(value, dict):
                    lines.append(f"\n[{key}]")
                    for k, v in value.items():
                        lines.append(f"  {k}: {v}")
                elif isinstance(value, list):
                    lines.append(f"\n[{key}] ({len(value)} items)")
                    for i, item in enumerate(value[:5]):
                        if isinstance(item, dict):
                            lines.append(f"  {i+1}. {json.dumps(item, ensure_ascii=False)[:100]}")
                        else:
                            lines.append(f"  {i+1}. {item}")
                    if len(value) > 5:
                        lines.append(f"  ... and {len(value) - 5} more")
                else:
                    lines.append(f"  {key}: {value}")
            return "\n".join(lines)
        if isinstance(data, list):
            out_lines = []
            for i, item in enumerate(data[:20]):
                if isinstance(item, (dict, list)):
                    out_lines.append(f"{i+1}. {json.dumps(item, ensure_ascii=False)[:150]}")
                else:
                    out_lines.append(f"{i+1}. {item}")
            return "\n".join(out_lines)
        return str(data)

    async def execute_command(self, command: str) -> str:
        command = command.strip()
        if not command:
            return ""
        self._add_to_history(command)
        parts = shlex.split(command)
        if not parts:
            return ""
        cmd = parts[0].lower()
        args = parts[1:]
        if cmd in ("help", "?"):
            return await self._show_help()
        if cmd == "history":
            return await self._show_history()
        if cmd == "clear":
            return "\033[2J\033[H"
        if cmd == "plugins":
            return await self._list_plugins()
        if cmd == "exit" or cmd == "quit":
            return "Goodbye."
        return f"Unknown command: {cmd}. Type 'help' for available commands."

    def _add_to_history(self, command: str):
        self._history.append(command)
        if len(self._history) > self._max_history:
            self._history.pop(0)

    async def _show_help(self) -> str:
        return """J.A.R.V.I.S CLI Commands:
  help, ?         Show this help
  history         Show command history
  plugins         List loaded plugins
  clear           Clear screen
  exit, quit      Exit CLI
  [plugin commands]  Any registered plugin tool"""

    async def _show_history(self) -> str:
        if not self._history:
            return "No commands in history."
        lines = []
        start = max(0, len(self._history) - 20)
        for i in range(start, len(self._history)):
            lines.append(f"  {i+1:4d}  {self._history[i]}")
        return "\n".join(lines)

    async def _list_plugins(self) -> str:
        from plugins.plugin_manager import get_plugin_manager
        pm = get_plugin_manager()
        plugins = pm.get_all_plugins()
        if not plugins:
            return "No plugins loaded."
        lines = [f"Loaded plugins ({len(plugins)}):"]
        for p in plugins:
            status = "ENABLED" if p.enabled else "DISABLED"
            lines.append(f"  {p.manifest.name:20s} v{p.manifest.version:6s} [{status}]")
        return "\n".join(lines)


manifest = PluginManifest(
    name="cli",
    version="1.0.0",
    description="CLI interface - command history, tab completion, color output",
)
