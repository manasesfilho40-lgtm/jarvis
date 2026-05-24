import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

from plugins.plugin_base import BasePlugin, PluginManifest, HookType

logger = logging.getLogger("plugin_whatsapp")

try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


class WhatsAppPlugin(BasePlugin):
    def __init__(self, manifest: Optional[PluginManifest] = None):
        if manifest is None:
            manifest = PluginManifest(
                name="whatsapp",
                version="1.0.0",
                description="WhatsApp Web integration via Playwright",
            )
        super().__init__(manifest)
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._playwright: Any = None
        self._connected: bool = False
        self._data_dir: str = ""
        self._headless: bool = False
        self._message_handler: Optional[callable] = None

    async def on_load(self):
        self._data_dir = self.config.get("whatsapp_data_dir", "")
        self._headless = bool(self.config.get("whatsapp_headless", False))
        if not self._data_dir:
            self._data_dir = str(Path(__file__).resolve().parent.parent / "data" / "whatsapp_session")
        logger.info("WhatsApp plugin loaded (run connect() to start session)")

    async def on_unload(self):
        await self.disconnect()
        logger.info("WhatsApp plugin unloaded")

    async def connect(self) -> bool:
        if self._connected:
            return True
        if not HAS_PLAYWRIGHT:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return False
        try:
            self._playwright = await async_playwright().start()
            user_data_dir = Path(self._data_dir)
            user_data_dir.mkdir(parents=True, exist_ok=True)

            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=self._headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
                viewport={"width": 1280, "height": 720},
            )

            self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
            await self._page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=30000)

            try:
                await self._page.wait_for_selector('[data-testid="chat-list"]', timeout=45000)
                self._connected = True
                logger.info("WhatsApp Web connected")
            except Exception:
                qr_visible = await self._page.is_visible('[data-testid="qrcode"]', timeout=5000)
                if qr_visible:
                    logger.info("WhatsApp Web - QR code detected, scan to connect")
                    try:
                        await self._page.wait_for_selector('[data-testid="chat-list"]', timeout=120000)
                        self._connected = True
                        logger.info("WhatsApp Web connected after QR scan")
                    except Exception:
                        logger.error("WhatsApp Web - QR scan timeout")
                        return False
                else:
                    logger.error("WhatsApp Web - could not detect chat list or QR code")
                    return False

            asyncio.create_task(self._poll_messages())
            return True
        except Exception as e:
            logger.error(f"Failed to connect WhatsApp: {e}")
            await self.disconnect()
            return False

    async def disconnect(self):
        self._connected = False
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        self._page = None

    async def send_message(self, contact: str, message: str) -> bool:
        if not self._connected or not self._page:
            return False
        try:
            search_box = self._page.locator('[data-testid="chat-list-search"]')
            if await search_box.is_visible():
                await search_box.fill("")
                await search_box.fill(contact)
                await asyncio.sleep(1)

            contact_elem = self._page.locator(f'[data-testid="conversation-info-header"]:has-text("{contact}")')
            chat_item = self._page.locator(f'[data-testid="chat-list"] >> text="{contact}"').first
            if await chat_item.is_visible(timeout=3000):
                await chat_item.click()
            else:
                await self._page.goto(f"https://web.whatsapp.com/send?phone={contact}", wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2)

            textbox = self._page.locator('[data-testid="conversation-compose-box-input"]')
            if not await textbox.is_visible(timeout=5000):
                textbox = self._page.locator('footer div[contenteditable="true"]')
            if not await textbox.is_visible(timeout=5000):
                logger.error("Could not find message input")
                return False

            await textbox.fill(message)
            await asyncio.sleep(0.3)

            send_btn = self._page.locator('[data-testid="compose-btn-send"]')
            if await send_btn.is_visible():
                await send_btn.click()
            else:
                await self._page.keyboard.press("Enter")

            logger.info(f"WhatsApp message sent to {contact}")
            return True
        except Exception as e:
            logger.error(f"Failed to send WhatsApp message: {e}")
            return False

    async def get_recent_messages(self, limit: int = 10) -> list[dict]:
        if not self._connected or not self._page:
            return []
        try:
            messages = await self._page.evaluate(f"""
                () => {{
                    const items = document.querySelectorAll('[data-testid="conversation-panel-messages"] [data-testid="message-content"]');
                    const results = [];
                    const start = Math.max(0, items.length - {limit});
                    for (let i = start; i < items.length; i++) {{
                        const text = items[i].querySelector('span.selectable-text');
                        const time = items[i].closest('[data-testid="message-content"]')?.querySelector('[data-testid="message-metadata"]');
                        results.push({{
                            text: text ? text.textContent : '',
                            time: time ? time.textContent : '',
                        }});
                    }}
                    return results;
                }}
            """)
            return messages if isinstance(messages, list) else []
        except Exception as e:
            logger.error(f"Failed to get recent messages: {e}")
            return []

    async def set_message_handler(self, handler: callable):
        self._message_handler = handler

    async def _poll_messages(self):
        last_count = 0
        while self._connected:
            try:
                messages = await self.get_recent_messages(5)
                if len(messages) > last_count and self._message_handler:
                    for msg in messages[last_count:]:
                        try:
                            if callable(self._message_handler):
                                result = self._message_handler(msg)
                                if hasattr(result, "__await__"):
                                    await result
                        except Exception as e:
                            logger.error(f"Message handler error: {e}")
                last_count = len(messages)
            except Exception:
                pass
            await asyncio.sleep(3)


manifest = PluginManifest(
    name="whatsapp",
    version="1.0.0",
    description="WhatsApp Web integration via Playwright",
)
