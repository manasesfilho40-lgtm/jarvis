import asyncio
import json
import logging
import time
from typing import Any, Optional

from agents.agent_base import BaseAgent
from core.event_bus import EventType, get_bus
from core.runtime import get_runtime

logger = logging.getLogger("reflection_agent")


class ReflectionAgent(BaseAgent):
    def __init__(self, reflection_interval: float = 60.0):
        super().__init__("reflection", "Self-critique, performance analysis, and continuous improvement")
        self.reflection_interval = reflection_interval
        self._last_reflection = 0.0
        self._performance_log: list[dict] = []
        self._max_perf_log = 100
        self._insights: list[str] = []
        self._improvement_suggestions: list[dict] = []

    async def think(self, context: dict) -> Optional[dict]:
        now = time.time()
        if now - self._last_reflection < self.reflection_interval:
            return None

        self._last_reflection = now
        self.status = self.__class__.status.__class__.THINKING

        thought = {
            "action": "reflect",
            "timestamp": now,
            "performance_summary": self._analyze_performance(),
            "recent_events": self._get_recent_events(),
            "suggestions": self._generate_suggestions(),
        }

        return thought

    async def act(self, thought: dict) -> Any:
        self.status = self.__class__.status.__class__.RUNNING

        if thought.get("suggestions"):
            for suggestion in thought["suggestions"]:
                self._improvement_suggestions.append(suggestion)
                self._bus.emit(EventType.IMPROVEMENT_PROPOSED, suggestion, source=self.name)

        self._bus.emit(EventType.REFLECTION_COMPLETE, {
            "summary": thought.get("performance_summary", ""),
            "suggestions_count": len(thought.get("suggestions", [])),
        }, source=self.name)

        return thought

    async def observe(self, event) -> Optional[dict]:
        event_type = event.type

        if event_type in (EventType.TASK_COMPLETED, EventType.TASK_FAILED):
            self._performance_log.append({
                "event": event_type.value,
                "data": event.data,
                "timestamp": time.time(),
            })
            if len(self._performance_log) > self._max_perf_log:
                self._performance_log = self._performance_log[-self._max_perf_log:]

        if event_type == EventType.ERROR_DETECTED:
            self._performance_log.append({
                "event": "error",
                "data": event.data,
                "timestamp": time.time(),
            })

        return {"event": event_type.value, "logged": True}

    def _analyze_performance(self) -> dict:
        recent = self._performance_log[-20:] if len(self._performance_log) > 20 else self._performance_log
        completed = sum(1 for e in recent if e["event"] == EventType.TASK_COMPLETED.value)
        failed = sum(1 for e in recent if e["event"] == EventType.TASK_FAILED.value)
        errors = sum(1 for e in recent if e["event"] == "error")

        total = completed + failed + errors
        success_rate = (completed / total * 100) if total > 0 else 100.0

        return {
            "period": f"last {len(recent)} events",
            "completed": completed,
            "failed": failed,
            "errors": errors,
            "success_rate": round(success_rate, 1),
            "total_analyzed": total,
        }

    def _get_recent_events(self) -> list[dict]:
        return [
            {"event": e["event"], "time_ago": f"{time.time() - e['timestamp']:.0f}s"}
            for e in self._performance_log[-10:]
        ]

    def _generate_suggestions(self) -> list[dict]:
        suggestions = []
        perf = self._analyze_performance()

        if perf["failed"] > perf["completed"] and perf["total_analyzed"] > 5:
            suggestions.append({
                "type": "performance",
                "severity": "high",
                "message": "High failure rate detected. Consider switching providers or adjusting tool parameters.",
                "action": "review_provider",
            })

        if perf["errors"] > 3:
            suggestions.append({
                "type": "stability",
                "severity": "medium",
                "message": "Multiple errors detected. Running self-diagnostics recommended.",
                "action": "run_diagnostics",
            })

        uptime = time.time() - self._runtime.state.started_at
        if uptime > 3600 and len(self._improvement_suggestions) == 0:
            suggestions.append({
                "type": "optimization",
                "severity": "low",
                "message": "System has been running for {:.0f} minutes. Consider memory compression.".format(uptime / 60),
                "action": "compress_memory",
            })

        return suggestions

    def get_insights(self) -> list[str]:
        return list(self._insights)

    def get_suggestions(self) -> list[dict]:
        return list(self._improvement_suggestions)

    def add_insight(self, insight: str):
        self._insights.append(insight)
        if len(self._insights) > 50:
            self._insights = self._insights[-50:]

    def subscribe_to_events(self):
        self.subscribe_to(
            EventType.TASK_COMPLETED,
            EventType.TASK_FAILED,
            EventType.ERROR_DETECTED,
            EventType.SYSTEM_ERROR,
        )
