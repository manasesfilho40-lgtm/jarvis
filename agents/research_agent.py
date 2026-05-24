import asyncio
import json
import logging
import re
import time
from typing import Any, Optional

import trafilatura
from agents.agent_base import BaseAgent
from core.event_bus import EventType, emit
from providers.provider_manager import get_manager

logger = logging.getLogger("research_agent")


class ResearchAgent(BaseAgent):
    def __init__(self, analyze_interval: float = 30.0):
        super().__init__("research", "Deep web research, scraping, and data extraction")
        self.analyze_interval = analyze_interval
        self._last_research_time = 0.0
        self._provider = get_manager()
        self._cache: dict[str, dict] = {}

    async def think(self, context: dict) -> Optional[dict]:
        return {"action": "idle", "agent": "research"}

    async def act(self, thought: dict) -> Any:
        return thought

    async def research(self, query: str, depth: str = "normal") -> dict:
        cache_key = f"{query}:{depth}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        emit(EventType.AGENT_THOUGHT, {"agent": "research", "thought": f"Researching: {query}"}, source="research")
        result = await self._deep_research(query, depth)
        self._cache[cache_key] = result
        if len(self._cache) > 100:
            self._cache.clear()
        return result

    async def _deep_research(self, query: str, depth: str) -> dict:
        if depth == "quick":
            return await self._quick_search(query)
        return await self._full_research(query)

    async def _quick_search(self, query: str) -> dict:
        try:
            from actions.web_search import web_search
            result = web_search(parameters={"query": query, "mode": "search"}, player=None)
            return {"query": query, "summary": str(result)[:2000], "sources": [], "depth": "quick"}
        except Exception as e:
            return {"query": query, "error": str(e), "depth": "quick"}

    async def _full_research(self, query: str) -> dict:
        try:
            from actions.web_search import web_search
            result = web_search(parameters={"query": query, "mode": "search"}, player=None)
            raw_text = str(result)
            urls = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', raw_text)
            urls = [u for u in urls if not any(x in u for x in ['google', 'youtube', 'facebook'])]
            urls = urls[:5]

            contents = []
            for url in urls:
                try:
                    downloaded = trafilatura.fetch_url(url)
                    if downloaded:
                        text = trafilatura.extract(downloaded)
                        if text and len(text) > 100:
                            contents.append({"url": url, "content": text[:3000]})
                except Exception:
                    continue
                await asyncio.sleep(0.5)

            prompt = f"""Research query: {query}

Search results: {raw_text[:3000]}

{"Extracted content:" if contents else ""}
{chr(10).join(f"Source {i+1}: {c['content'][:2000]}" for i, c in enumerate(contents[:3]))}

Provide a comprehensive research summary in Brazilian Portuguese. Include key findings, data points, and sources."""

            response = await self._provider.generate_async(prompt, temperature=0.3)
            summary = response.text

            result_data = {
                "query": query,
                "summary": summary,
                "sources": urls[:5],
                "extracted_pages": len(contents),
                "depth": "full",
            }
            emit(EventType.MEMORY_SAVED, {"type": "research", "query": query, "summary": summary[:200]}, source="research")
            return result_data
        except Exception as e:
            return {"query": query, "error": str(e), "depth": "full"}

    async def extract_from_url(self, url: str) -> Optional[str]:
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                return trafilatura.extract(downloaded)
            return None
        except Exception:
            return None

    async def compare_sources(self, query: str, items: list[str], aspect: str = "") -> str:
        prompt = f"""Compare these items regarding: {query}
Aspect: {aspect if aspect else 'general comparison'}

Items:
{chr(10).join(f'- {item}' for item in items)}

Provide a structured comparison in Brazilian Portuguese."""

        response = await self._provider.generate_async(prompt, temperature=0.3)
        return response.text

    def subscribe_to_events(self):
        self.subscribe_to(EventType.USER_INPUT, EventType.TASK_CREATED)


_research_agent_instance = None


def get_research_agent() -> ResearchAgent:
    global _research_agent_instance
    if _research_agent_instance is None:
        _research_agent_instance = ResearchAgent()
    return _research_agent_instance
