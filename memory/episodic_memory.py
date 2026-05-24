import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from collections import defaultdict

from core.event_bus import EventType, get_bus
from memory.vector_memory import MemoryStore, get_vector_memory

logger = logging.getLogger("episodic_memory")


@dataclass
class Episode:
    id: str
    timestamp: float
    event_type: str
    content: str
    context: dict = field(default_factory=dict)
    summary: str = ""
    importance: float = 0.5
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "timestamp": self.timestamp,
            "event_type": self.event_type, "content": self.content,
            "context": self.context, "summary": self.summary,
            "importance": self.importance, "tags": self.tags,
        }


class EpisodicMemory:
    def __init__(self):
        self._bus = get_bus()
        self._vector = get_vector_memory()
        self._episodes: list[Episode] = []
        self._max_episodes = 1000
        self._summary_interval = 50
        self._summary_threshold = 0.7
        self._listening = False
        self._session_start = time.time()
        self._event_counts: dict[str, int] = defaultdict(int)

    def start(self):
        if self._listening:
            return
        self._listening = True
        self._bus.subscribe(EventType.AGENT_ACTION, self._on_action, source="episodic")
        self._bus.subscribe(EventType.AGENT_THOUGHT, self._on_thought, source="episodic")
        self._bus.subscribe(EventType.TASK_COMPLETED, self._on_task, source="episodic")
        self._bus.subscribe(EventType.TASK_FAILED, self._on_task, source="episodic")
        self._bus.subscribe(EventType.ERROR_DETECTED, self._on_error, source="episodic")
        self._bus.subscribe(EventType.MEMORY_SAVED, self._on_memory, source="episodic")
        self._bus.subscribe(EventType.USER_INPUT, self._on_user_input, source="episodic")
        logger.info("EpisodicMemory started")

    def stop(self):
        self._listening = False
        self._summarize_and_compress()

    def _on_action(self, event):
        data = event.data if isinstance(event.data, dict) else {}
        self._record("agent_action", f"Agent {data.get('agent', '?')}: {str(data.get('result', ''))[:200]}", {"agent": data.get("agent", "")})

    def _on_thought(self, event):
        data = event.data if isinstance(event.data, dict) else {}
        thought = data.get("thought", "")
        if isinstance(thought, dict):
            thought = str(thought)
        if thought:
            self._record("agent_thought", str(thought)[:300], {"agent": data.get("agent", "")})

    def _on_task(self, event):
        data = event.data if isinstance(event.data, dict) else {}
        status = "completed" if event.type == EventType.TASK_COMPLETED else "failed"
        self._record(f"task_{status}", str(data.get("result", str(data)))[:200], {"status": status})

    def _on_error(self, event):
        data = event.data if isinstance(event.data, dict) else {}
        self._record("error", str(data.get("message", str(data)))[:200], {"severity": data.get("severity", "unknown")}, importance=0.8)

    def _on_memory(self, event):
        data = event.data if isinstance(event.data, dict) else {}
        self._record("memory", str(data)[:200], {"type": data.get("type", "general")}, importance=0.6)

    def _on_user_input(self, event):
        data = event.data
        text = data if isinstance(data, str) else (data.get("text", "") if isinstance(data, dict) else "")
        if text:
            self._record("user_input", text[:200], importance=0.7)

    def _record(self, event_type: str, content: str, context: dict = None, importance: float = 0.5):
        if not content:
            return
        self._event_counts[event_type] += 1
        episode = Episode(
            id=f"ep_{int(time.time())}_{len(self._episodes)}",
            timestamp=time.time(),
            event_type=event_type,
            content=content,
            context=context or {},
            importance=importance,
        )
        self._episodes.append(episode)
        if len(self._episodes) > self._max_episodes:
            removed = self._episodes.pop(0)
            self._store_episode(removed)
        if len(self._episodes) % self._summary_interval == 0:
            self._summarize_batch()

    def _store_episode(self, episode: Episode):
        self._vector.store(
            content=episode.content,
            store=MemoryStore.EPISODIC,
            metadata={
                "event_type": episode.event_type,
                "timestamp": episode.timestamp,
                "importance": episode.importance,
                "summary": episode.summary or "",
            },
        )

    def _summarize_batch(self):
        try:
            from providers.provider_manager import get_manager
            pm = get_manager()
            recent = self._episodes[-self._summary_interval:]
            text = "\n".join(f"[{e.event_type}] {e.content[:100]}" for e in recent)
            prompt = f"""Summarize these recent events into key insights. Focus on patterns, important actions, and context:

{text[:2000]}

Return a concise summary in Brazilian Portuguese (max 100 words):"""
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                response = loop.run_until_complete(pm.generate_async(prompt, temperature=0.3))
                loop.close()
                summary = response.text.strip()
                for e in recent:
                    e.summary = summary[:200]
                self._vector.store(content=summary, store=MemoryStore.SUMMARIES, metadata={"type": "auto_summary", "count": len(recent)})
                logger.info(f"Episodic summary: {summary[:80]}...")
            except Exception as e:
                logger.warning(f"Summary generation failed: {e}")
        except Exception as e:
            logger.warning(f"Summarization error: {e}")

    def _summarize_and_compress(self):
        if len(self._episodes) < 10:
            return
        try:
            self._summarize_batch()
            text = "\n".join(f"[{e.event_type}] {e.content[:100]}" for e in self._episodes[-20:])
            prompt = f"""Generate session summary from these events:

{text[:2000]}

Session insights in Brazilian Portuguese (max 150 words):"""
            from providers.provider_manager import get_manager
            pm = get_manager()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(pm.generate_async(prompt, temperature=0.3))
            loop.close()
            summary = response.text.strip()
            self._vector.store(content=summary, store=MemoryStore.SUMMARIES, metadata={"type": "session_summary", "session_start": self._session_start})
        except Exception as e:
            logger.warning(f"Compression error: {e}")

    def recall(self, query: str, n: int = 5) -> list[Episode]:
        results = self._vector.search(query, store=MemoryStore.EPISODIC, n_results=n)
        episodes = []
        for r in results:
            episodes.append(Episode(
                id=r.id, timestamp=r.metadata.get("timestamp", 0),
                event_type=r.metadata.get("event_type", "unknown"),
                content=r.content, summary=r.metadata.get("summary", ""),
                importance=r.metadata.get("importance", 0.5),
            ))
        return episodes

    def get_recent(self, n: int = 10) -> list[Episode]:
        return self._episodes[-n:]

    def get_stats(self) -> dict:
        return {
            "total_episodes": len(self._episodes),
            "event_counts": dict(self._event_counts),
            "session_duration_s": time.time() - self._session_start,
            "has_summaries": self._vector.count(MemoryStore.SUMMARIES),
        }


_episodic_memory_instance = None


def get_episodic_memory() -> EpisodicMemory:
    global _episodic_memory_instance
    if _episodic_memory_instance is None:
        _episodic_memory_instance = EpisodicMemory()
    return _episodic_memory_instance
