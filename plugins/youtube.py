import asyncio
import logging
from typing import Any, Optional

from plugins.plugin_base import BasePlugin, PluginManifest, HookType

logger = logging.getLogger("plugin_youtube")

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    HAS_TRANSCRIPT = True
except ImportError:
    HAS_TRANSCRIPT = False


class YouTubePlugin(BasePlugin):
    def __init__(self, manifest: Optional[PluginManifest] = None):
        if manifest is None:
            manifest = PluginManifest(
                name="youtube",
                version="1.0.0",
                description="YouTube integration - search, video info, transcripts",
            )
        super().__init__(manifest)

    async def on_load(self):
        logger.info("YouTube plugin loaded")

    async def on_unload(self):
        logger.info("YouTube plugin unloaded")

    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.videos(query, max_results=max_results))
                return [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("content", "") or r.get("url", ""),
                        "duration": r.get("duration", ""),
                        "views": r.get("views", ""),
                        "description": r.get("description", "")[:200],
                    }
                    for r in results
                ]
        except Exception as e:
            logger.error(f"YouTube search failed: {e}")
            return []

    async def get_video_info(self, video_id: str) -> Optional[dict]:
        try:
            import requests
            from urllib.parse import urlencode
            url = f"https://www.youtube.com/watch?v={video_id}"
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                return None

            import re
            title_match = re.search(r'<title>(.*?)<\/title>', resp.text)
            title = title_match.group(1).replace(" - YouTube", "").strip() if title_match else "Unknown"

            views_match = re.search(r'([\d,.]+)\s*views', resp.text)
            views = views_match.group(1) if views_match else "Unknown"

            return {
                "id": video_id,
                "title": title,
                "url": url,
                "views": views,
                "thumbnail": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
            }
        except Exception as e:
            logger.error(f"Failed to get video info: {e}")
            return None

    def _extract_video_id(self, url_or_id: str) -> Optional[str]:
        import re
        patterns = [
            r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
            r'^([a-zA-Z0-9_-]{11})$',
        ]
        for pattern in patterns:
            match = re.search(pattern, url_or_id)
            if match:
                return match.group(1)
        return None

    async def get_transcript(self, video_id: str, languages: list[str] = None) -> Optional[list[dict]]:
        if not HAS_TRANSCRIPT:
            return None
        try:
            vid = self._extract_video_id(video_id) or video_id
            transcript = YouTubeTranscriptApi.get_transcript(vid, languages=languages or ["pt", "en"])
            return [
                {"text": t["text"], "start": t["start"], "duration": t["duration"]}
                for t in transcript
            ]
        except Exception as e:
            logger.error(f"Failed to get transcript: {e}")
            return None

    async def get_transcript_text(self, video_id: str, languages: list[str] = None) -> Optional[str]:
        transcript = await self.get_transcript(video_id, languages)
        if transcript:
            return " ".join(t["text"] for t in transcript)
        return None

    async def search_and_get_first(self, query: str) -> Optional[dict]:
        results = await self.search(query, max_results=1)
        return results[0] if results else None


manifest = PluginManifest(
    name="youtube",
    version="1.0.0",
    description="YouTube integration - search, video info, transcripts",
)
