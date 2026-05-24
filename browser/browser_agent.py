import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("browser_agent")


try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    logger.warning("Playwright not installed. Install with: pip install playwright && playwright install")


@dataclass
class PageInfo:
    title: str = ""
    url: str = ""
    content_snippet: str = ""
    text_content: str = ""
    viewport_size: tuple[int, int] = (0, 0)
    scroll_position: tuple[int, int] = (0, 0)
    links: list[dict] = field(default_factory=list)
    buttons: list[dict] = field(default_factory=list)
    inputs: list[dict] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    load_time_ms: float = 0.0


@dataclass
class BrowserSession:
    context: Any = None
    page: Any = None
    active_url: str = ""
    created_at: float = 0.0
    pages: list[Any] = field(default_factory=list)


class BrowserAgent:
    def __init__(self, headless: bool = False, browser_type: str = "chromium", user_data_dir: str = ""):
        self.headless = headless
        self.browser_type = browser_type
        self.user_data_dir = user_data_dir or str(Path.home() / ".jarvis_browser_profile")
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._session: Optional[BrowserSession] = None
        self._default_timeout = 30000
        self._screenshot_dir = str(Path.home() / "Desktop" / "jarvis_screenshots")
        os.makedirs(self._screenshot_dir, exist_ok=True)

    async def start(self):
        if not HAS_PLAYWRIGHT:
            logger.error("Playwright not available")
            return False
        try:
            self._playwright = await async_playwright().start()
            browser_launcher = getattr(self._playwright, self.browser_type)

            if os.path.exists(self.user_data_dir):
                context = await browser_launcher.launch_persistent_context(
                    user_data_dir=self.user_data_dir,
                    headless=self.headless,
                    args=["--disable-blink-features=AutomationControlled"],
                    no_viewport=False,
                )
                self._browser = context.browser
                self._session = BrowserSession(context=context, created_at=time.time())
            else:
                self._browser = await browser_launcher.launch(
                    headless=self.headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                context = await self._browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )
                self._session = BrowserSession(context=context, created_at=time.time())

            page = await context.new_page()
            self._session.page = page
            self._session.pages.append(page)
            logger.info(f"Browser started ({self.browser_type})")
            return True
        except Exception as e:
            logger.error(f"Browser start failed: {e}")
            return False

    async def stop(self):
        try:
            if self._session and self._session.context:
                await self._session.context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            self._session = None
            self._browser = None
            self._playwright = None
            logger.info("Browser stopped")
        except Exception as e:
            logger.error(f"Browser stop failed: {e}")

    async def navigate(self, url: str, timeout: int = 30000) -> PageInfo:
        if not self._session or not self._session.page:
            raise RuntimeError("Browser not started")
        start = time.time()
        page = self._session.page
        try:
            await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        info = await self._get_page_info(page)
        info.load_time_ms = (time.time() - start) * 1000
        self._session.active_url = info.url
        logger.info(f"Navigated to {url} -> {info.title} ({info.load_time_ms:.0f}ms)")
        return info

    async def _get_page_info(self, page: Any) -> PageInfo:
        try:
            title = await page.title()
            url = page.url
            viewport = await page.evaluate("({width: window.innerWidth, height: window.innerHeight})")

            headings = await page.evaluate("""() =>
                Array.from(document.querySelectorAll('h1, h2, h3')).map(h => h.textContent.trim())
            """)

            links = await page.evaluate("""() =>
                Array.from(document.querySelectorAll('a[href]')).slice(0, 50).map(a => ({
                    text: a.textContent.trim().slice(0, 100),
                    href: a.href,
                }))
            """)

            buttons = await page.evaluate("""() =>
                Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"], [role="button"]')).slice(0, 50).map(b => ({
                    text: b.textContent.trim().slice(0, 100) || b.value?.slice(0, 100) || '',
                    type: b.tagName.toLowerCase(),
                }))
            """)

            inputs = await page.evaluate("""() =>
                Array.from(document.querySelectorAll('input:not([type="hidden"]), textarea, select')).slice(0, 50).map(i => ({
                    type: i.type || i.tagName.toLowerCase(),
                    name: i.name || '',
                    placeholder: i.placeholder || '',
                    id: i.id || '',
                }))
            """)

            text_content = await page.evaluate("""() => {
                const article = document.querySelector('article, main, .content, #content');
                if (article) return article.textContent.trim().slice(0, 5000);
                return document.body.textContent.trim().slice(0, 3000);
            }""")

            scroll = await page.evaluate("({x: window.scrollX, y: window.scrollY})")

            return PageInfo(
                title=title,
                url=url,
                text_content=text_content,
                content_snippet=text_content[:500],
                viewport_size=(viewport["width"], viewport["height"]),
                scroll_position=(scroll["x"], scroll["y"]),
                links=links,
                buttons=buttons,
                inputs=inputs,
                headings=headings,
            )
        except Exception as e:
            logger.error(f"Get page info failed: {e}")
            return PageInfo()

    async def click(self, selector: str = "", text: str = "") -> bool:
        page = self._get_page()
        try:
            if selector:
                await page.click(selector, timeout=self._default_timeout)
            elif text:
                await page.click(f"text={text}", timeout=self._default_timeout)
            else:
                return False
            await asyncio.sleep(0.5)
            return True
        except Exception as e:
            logger.error(f"Click failed: {e}")
            return False

    async def type_text(self, selector: str, text: str, clear_first: bool = True):
        page = self._get_page()
        try:
            if clear_first:
                await page.fill(selector, text)
            else:
                await page.type(selector, text, delay=10)
            return True
        except Exception as e:
            logger.error(f"Type text failed: {e}")
            return False

    async def type_in_field(self, field_info: str, text: str):
        page = self._get_page()
        selectors = [
            f'input[name="{field_info}"]',
            f'input[placeholder="{field_info}"]',
            f'input[id="{field_info}"]',
            f'textarea[name="{field_info}"]',
            f'textarea[placeholder="{field_info}"]',
            f'[aria-label="{field_info}"]',
        ]
        for sel in selectors:
            try:
                el = await page.wait_for_selector(sel, timeout=3000)
                if el:
                    await el.fill(text)
                    return True
            except Exception:
                continue
        return False

    async def scroll(self, direction: str = "down", amount: int = 500):
        page = self._get_page()
        try:
            if direction == "down":
                await page.evaluate(f"window.scrollBy(0, {amount})")
            elif direction == "up":
                await page.evaluate(f"window.scrollBy(0, -{amount})")
            elif direction == "bottom":
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            elif direction == "top":
                await page.evaluate("window.scrollTo(0, 0)")
            return True
        except Exception as e:
            logger.error(f"Scroll failed: {e}")
            return False

    async def get_text(self, selector: str = "") -> str:
        page = self._get_page()
        try:
            if selector:
                el = await page.wait_for_selector(selector, timeout=5000)
                if el:
                    return await el.text_content() or ""
            return await page.evaluate("document.body.innerText.slice(0, 10000)")
        except Exception as e:
            logger.error(f"Get text failed: {e}")
            return ""

    async def screenshot(self, path: str = "") -> str:
        page = self._get_page()
        if not path:
            path = os.path.join(self._screenshot_dir, f"screenshot_{int(time.time())}.png")
        try:
            await page.screenshot(path=path, full_page=True)
            logger.info(f"Screenshot saved: {path}")
            return path
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return ""

    async def new_tab(self, url: str = ""):
        context = self._get_context()
        page = await context.new_page()
        self._session.pages.append(page)
        self._session.page = page
        if url:
            await self.navigate(url)
        return page

    async def switch_tab(self, index: int = -1):
        pages = self._session.pages if self._session else []
        if not pages:
            return
        if index < 0 or index >= len(pages):
            index = -1
        self._session.page = pages[index]
        logger.info(f"Switched to tab {index}: {await pages[index].title()}")

    async def close_tab(self):
        if self._session and len(self._session.pages) > 1:
            page = self._session.page
            await page.close()
            self._session.pages.remove(page)
            self._session.page = self._session.pages[-1] if self._session.pages else None
            logger.info("Tab closed")

    async def execute_js(self, script: str) -> Any:
        page = self._get_page()
        try:
            return await page.evaluate(script)
        except Exception as e:
            logger.error(f"JS execution failed: {e}")
            return None

    async def extract_links(self) -> list[dict]:
        info = await self._get_page_info(self._get_page())
        return info.links

    async def search(self, query: str, engine: str = "google") -> PageInfo:
        urls = {
            "google": f"https://www.google.com/search?q={query}",
            "duckduckgo": f"https://duckduckgo.com/?q={query}",
            "bing": f"https://www.bing.com/search?q={query}",
        }
        url = urls.get(engine, urls["google"])
        return await self.navigate(url)

    async def get_page_source(self) -> str:
        page = self._get_page()
        try:
            return await page.content()
        except Exception as e:
            logger.error(f"Get source failed: {e}")
            return ""

    async def wait_for_element(self, selector: str, timeout: int = 10000) -> bool:
        page = self._get_page()
        try:
            await page.wait_for_selector(selector, timeout=timeout)
            return True
        except Exception:
            return False

    async def fill_form(self, data: dict[str, str]) -> dict[str, bool]:
        results = {}
        for field_name, value in data.items():
            ok = await self.type_in_field(field_name, value)
            results[field_name] = ok
        return results

    def _get_page(self):
        if not self._session or not self._session.page:
            raise RuntimeError("Browser session not active")
        return self._session.page

    def _get_context(self):
        if not self._session or not self._session.context:
            raise RuntimeError("Browser session not active")
        return self._session.context

    def is_running(self) -> bool:
        return self._session is not None and self._browser is not None

    async def get_status(self) -> dict:
        if not self.is_running():
            return {"running": False}
        try:
            page = self._get_page()
            return {
                "running": True,
                "url": page.url,
                "title": await page.title(),
                "tabs": len(self._session.pages) if self._session else 0,
            }
        except Exception:
            return {"running": True}

    def __repr__(self):
        return f"BrowserAgent(type={self.browser_type}, headless={self.headless})"
