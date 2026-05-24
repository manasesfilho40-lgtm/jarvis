import asyncio
import logging
from typing import Any, Optional

from agents.agent_base import BaseAgent
from browser.browser_agent import BrowserAgent

logger = logging.getLogger("browser_agent_wrapper")


class BrowserAgentWrapper(BaseAgent):
    def __init__(self, headless: bool = False):
        super().__init__("browser_agent", "Autonomous web navigation and browser automation")
        self._browser: Optional[BrowserAgent] = None
        self._headless = headless
        self._current_task: Optional[dict] = None

    async def think(self, context: dict) -> Optional[dict]:
        return {"action": "check_status", "browser_running": self._browser.is_running() if self._browser else False}

    async def act(self, thought: dict) -> Any:
        return thought

    async def ensure_browser(self) -> BrowserAgent:
        if self._browser is None:
            self._browser = BrowserAgent(headless=self._headless)
            await self._browser.start()
        return self._browser

    async def navigate(self, url: str) -> dict:
        browser = await self.ensure_browser()
        info = await browser.navigate(url)
        return {
            "title": info.title,
            "url": info.url,
            "text_length": len(info.text_content),
            "links": len(info.links),
            "buttons": len(info.buttons),
            "inputs": len(info.inputs),
            "headings": info.headings[:10],
        }

    async def search(self, query: str, engine: str = "google") -> dict:
        browser = await self.ensure_browser()
        info = await browser.search(query, engine)
        return {
            "title": info.title,
            "url": info.url,
            "text_snippet": info.content_snippet[:500],
            "links": info.links[:20],
        }

    async def click(self, selector: str = "", text: str = "") -> bool:
        browser = await self.ensure_browser()
        return await browser.click(selector, text)

    async def type_text(self, selector: str, text: str, clear_first: bool = True) -> bool:
        browser = await self.ensure_browser()
        return await browser.type_text(selector, text, clear_first)

    async def screenshot(self, path: str = "") -> str:
        browser = await self.ensure_browser()
        return await browser.screenshot(path)

    async def extract_text(self) -> str:
        browser = await self.ensure_browser()
        return await browser.get_text()

    async def scroll(self, direction: str = "down", amount: int = 500) -> bool:
        browser = await self.ensure_browser()
        return await browser.scroll(direction, amount)

    async def get_page_info(self) -> dict:
        if not self._browser or not self._browser.is_running():
            return {"running": False}
        return await self._browser.get_status()

    async def close(self):
        if self._browser:
            await self._browser.stop()
            self._browser = None

    async def observe(self, event) -> Optional[dict]:
        return None


_browser_wrapper_instance = None


def get_browser_wrapper(headless: bool = False) -> BrowserAgentWrapper:
    global _browser_wrapper_instance
    if _browser_wrapper_instance is None:
        _browser_wrapper_instance = BrowserAgentWrapper(headless=headless)
    return _browser_wrapper_instance
