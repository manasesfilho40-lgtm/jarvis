import asyncio
import json
import logging
import re
from typing import Any, Optional
from urllib.parse import urlparse

from plugins.plugin_base import BasePlugin, PluginManifest, HookType

logger = logging.getLogger("plugin_web_scraper")


class WebScraperPlugin(BasePlugin):
    def __init__(self, manifest: Optional[PluginManifest] = None):
        if manifest is None:
            manifest = PluginManifest(
                name="web_scraper",
                version="1.0.0",
                description="Web scraping - extract content, text, metadata from URLs",
            )
        super().__init__(manifest)
        self._user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    async def on_load(self):
        logger.info("WebScraper plugin loaded")

    async def on_unload(self):
        logger.info("WebScraper plugin unloaded")

    async def scrape_url(self, url: str) -> Optional[dict]:
        try:
            import requests
            from bs4 import BeautifulSoup
            headers = {"User-Agent": self._user_agent}
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            title = soup.title.string.strip() if soup.title and soup.title.string else ""
            meta_desc = ""
            meta_tag = soup.find("meta", attrs={"name": "description"})
            if meta_tag and meta_tag.get("content"):
                meta_desc = meta_tag["content"].strip()

            text = soup.get_text(separator=" ", strip=True)
            text = re.sub(r'\s+', ' ', text)

            links = []
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                if href.startswith("/"):
                    parsed = urlparse(url)
                    href = f"{parsed.scheme}://{parsed.netloc}{href}"
                links.append({"text": a_tag.get_text(strip=True)[:100], "url": href})

            images = []
            for img_tag in soup.find_all("img", src=True):
                src = img_tag["src"]
                if src.startswith("/"):
                    parsed = urlparse(url)
                    src = f"{parsed.scheme}://{parsed.netloc}{src}"
                images.append({"alt": img_tag.get("alt", ""), "url": src})

            return {
                "url": url,
                "title": title,
                "description": meta_desc or title,
                "text_length": len(text),
                "text_preview": text[:2000],
                "links_count": len(links),
                "links": links[:50],
                "images_count": len(images),
                "images": images[:20],
            }
        except Exception as e:
            logger.error(f"Failed to scrape {url}: {e}")
            return None

    async def extract_text(self, url: str) -> Optional[str]:
        result = await self.scrape_url(url)
        if result:
            return result.get("text_preview", "")
        return None

    async def extract_links(self, url: str) -> list[dict]:
        result = await self.scrape_url(url)
        if result:
            return result.get("links", [])
        return []

    async def search_and_scrape(self, query: str) -> Optional[dict]:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=1))
                if results:
                    url = results[0].get("href", "")
                    if url:
                        return await self.scrape_url(url)
            return None
        except Exception as e:
            logger.error(f"Search and scrape failed: {e}")
            return None


manifest = PluginManifest(
    name="web_scraper",
    version="1.0.0",
    description="Web scraping - extract content, text, metadata from URLs",
)
