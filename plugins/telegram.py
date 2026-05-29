import asyncio
import logging
import threading
from typing import Any, Optional

from plugins.plugin_base import BasePlugin, HookType, PluginManifest

logger = logging.getLogger("plugin_telegram")

try:
    from telegram import Bot, Update
    from telegram.ext import Application, MessageHandler, filters
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False


class TelegramPlugin(BasePlugin):
    def __init__(self, manifest: Optional[PluginManifest] = None):
        if manifest is None:
            manifest = PluginManifest(
                name="telegram",
                version="1.0.0",
                description="Telegram integration for JARVIS",
            )
        super().__init__(manifest)
        self._app: Optional[Application] = None
        self._token: str = ""
        self._chat_id: Optional[int] = None
        self._thread: Optional[threading.Thread] = None

    async def on_load(self):
        self._token = self.config.get("telegram_token", "")
        self._chat_id = self.config.get("telegram_chat_id")
        if self._token and HAS_TELEGRAM:
            self._app = Application.builder().token(self._token).build()
            self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
            self._thread = threading.Thread(target=self._run_polling, daemon=True)
            self._thread.start()
            logger.info("Telegram plugin loaded")

    def _run_polling(self):
        if self._app:
            try:
                self._app.run_polling()
            except Exception as e:
                logger.error(f"Telegram polling failed: {e}")

    async def _handle_message(self, update: Update, context):
        if not update.message or not update.message.text:
            return
        if self._chat_id and update.effective_chat.id != self._chat_id:
            return
        text = update.message.text
        author = update.effective_user.first_name if update.effective_user else "Unknown"
        from core.event_bus import emit as bus_emit, EventType
        bus_emit(EventType.USER_INPUT, {"text": text, "source": "telegram", "author": author}, source="telegram")
        bus_emit(EventType.UI_LOG_MESSAGE, f"[Telegram: {author}] {text}", source="telegram")

    async def send_message(self, chat_id: int, text: str) -> bool:
        if self._app and self._app.bot:
            try:
                await self._app.bot.send_message(chat_id=chat_id, text=text)
                return True
            except Exception as e:
                logger.error(f"Telegram send failed: {e}")
        return False

    async def send_to_configured_chat(self, text: str) -> bool:
        if self._chat_id:
            return await self.send_message(self._chat_id, text)
        return False

    async def on_unload(self):
        if self._app:
            await self._app.stop()
            await self._app.shutdown()
        logger.info("Telegram plugin unloaded")


manifest = PluginManifest(
    name="telegram",
    version="1.0.0",
    description="Telegram integration - send/receive messages",
#     hooks: see class docstring
#     tools: see class docstring
)
