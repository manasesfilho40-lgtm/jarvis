import asyncio
import logging
import threading
from typing import Any, Optional

from plugins.plugin_base import BasePlugin, HookType, PluginManifest

logger = logging.getLogger("plugin_discord")

try:
    import discord
    from discord.ext import commands
    HAS_DISCORD = True
except ImportError:
    HAS_DISCORD = False


class DiscordBot(commands.Bot if HAS_DISCORD else object):
    def __init__(self, on_message_callback=None):
        if HAS_DISCORD:
            intents = discord.Intents.default()
            intents.message_content = True
            super().__init__(command_prefix="!", intents=intents)
            self._callback = on_message_callback

    async def on_ready(self):
        logger.info(f"Discord bot logged in as {self.user}")

    async def on_message(self, message):
        if self._callback and not message.author.bot:
            await self._callback(message)


class DiscordPlugin(BasePlugin):
    def __init__(self, manifest: Optional[PluginManifest] = None):
        if manifest is None:
            manifest = PluginManifest(
                name="discord",
                version="1.0.0",
                description="Discord integration for JARVIS",
            )
        super().__init__(manifest)
        self._bot: Optional[DiscordBot] = None
        self._thread: Optional[threading.Thread] = None
        self._token: str = ""
        self._channel_id: Optional[int] = None

    async def on_load(self):
        self._token = self.config.get("discord_token", "")
        self._channel_id = self.config.get("discord_channel_id")
        if self._token and HAS_DISCORD:
            self._bot = DiscordBot(on_message_callback=self._handle_discord_message)
            self._thread = threading.Thread(target=self._run_bot, daemon=True)
            self._thread.start()
            logger.info("Discord plugin loaded")

    def _run_bot(self):
        if self._bot and self._token:
            try:
                self._bot.run(self._token)
            except Exception as e:
                logger.error(f"Discord bot failed: {e}")

    async def _handle_discord_message(self, message):
        if self._channel_id and message.channel.id != self._channel_id:
            return
        if isinstance(message, discord.Message):
            from core.event_bus import emit as bus_emit, EventType
            bus_emit(EventType.USER_INPUT, {"text": message.content, "source": "discord", "author": str(message.author)}, source="discord")
            bus_emit(EventType.UI_LOG_MESSAGE, f"[Discord: {message.author}] {message.content}", source="discord")

    async def send_message(self, channel_id: int, content: str):
        if self._bot and self._bot.is_ready():
            channel = self._bot.get_channel(channel_id)
            if channel:
                await channel.send(content)
                return True
        return False

    async def send_to_configured_channel(self, content: str):
        if self._channel_id:
            return await self.send_message(self._channel_id, content)
        return False

    async def on_unload(self):
        if self._bot:
            await self._bot.close()
        logger.info("Discord plugin unloaded")


manifest = PluginManifest(
    name="discord",
    version="1.0.0",
    description="Discord integration for JARVIS - send/receive messages, monitor channels",
#     hooks: see class docstring
#     tools: see class docstring
)
