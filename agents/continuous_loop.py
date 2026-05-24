import asyncio
import logging
import threading
import time
from enum import Enum
from typing import Any, Optional

from agents.agent_base import AgentStatus, BaseAgent
from core.event_bus import EventType, get_bus, emit
from core.runtime import get_runtime

logger = logging.getLogger("continuous_loop")


class LoopPhase(Enum):
    OBSERVE = "observe"
    THINK = "think"
    PLAN = "plan"
    EXECUTE = "execute"
    REFLECT = "reflect"
    LEARN = "learn"
    IDLE = "idle"


class ContinuousLoop:
    def __init__(self, orchestrator=None):
        self._orchestrator = orchestrator
        self._bus = get_bus()
        self._runtime = get_runtime()
        self._running = False
        self._loop_thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._current_phase = LoopPhase.IDLE
        self._cycle_count = 0
        self._last_cycle_time = 0.0
        self._cycle_times: list[float] = []
        self._agent_contexts: dict[str, Any] = {}
        self._idle_threshold = 30.0
        self._proactive_interval = 120.0
        self._last_proactive_check = 0.0
        self._auto_mode = False

    @property
    def current_phase(self) -> LoopPhase:
        return self._current_phase

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    def start(self):
        if self._running:
            return
        self._running = True
        self._loop_thread = threading.Thread(target=self._run, daemon=True, name="ContinuousLoop")
        self._loop_thread.start()
        logger.info("Continuous loop started")

    def stop(self):
        self._running = False
        logger.info("Continuous loop stopped")

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._main_loop())

    async def _main_loop(self):
        emit(EventType.SYSTEM_STARTUP, {"loop": "continuous", "started_at": time.time()}, source="continuous_loop")

        while self._running:
            cycle_start = time.time()
            self._cycle_count += 1

            try:
                await self._observe_phase()
                await self._think_phase()
                await self._plan_phase()
                await self._execute_phase()
                await self._reflect_phase()
                await self._learn_phase()
            except Exception as e:
                logger.error(f"Loop cycle {self._cycle_count} failed: {e}")
                emit(EventType.SYSTEM_ERROR, {
                    "cycle": self._cycle_count,
                    "error": str(e),
                }, source="continuous_loop")

            cycle_time = time.time() - cycle_start
            self._cycle_times.append(cycle_time)
            if len(self._cycle_times) > 100:
                self._cycle_times = self._cycle_times[-100:]
            self._last_cycle_time = cycle_time

            idle_seconds = self._runtime.get("idle_seconds", 0)
            if idle_seconds and idle_seconds > self._idle_threshold:
                await asyncio.sleep(min(self._idle_threshold, 10.0))
            else:
                await asyncio.sleep(0.5)

        emit(EventType.SYSTEM_SHUTDOWN, {"loop": "continuous"}, source="continuous_loop")

    async def _observe_phase(self):
        self._current_phase = LoopPhase.OBSERVE

        if self._orchestrator:
            observer = self._orchestrator.get_agent("observer")
            if observer:
                context = observer._build_context()
                thought = await observer.think(context)
                if thought:
                    await observer.act(thought)

        emit(EventType.AGENT_OBSERVATION, {
            "cycle": self._cycle_count,
            "phase": "observe",
        }, source="continuous_loop")

    async def _think_phase(self):
        self._current_phase = LoopPhase.THINK

        if self._orchestrator:
            for agent in self._orchestrator._agents.values():
                if agent.status == AgentStatus.RUNNING and hasattr(agent, 'think'):
                    try:
                        context = agent._build_context()
                        thought = await agent.think(context)
                        if thought:
                            self._agent_contexts[agent.name] = thought
                            emit(EventType.AGENT_THOUGHT, {
                                "agent": agent.name,
                                "thought": thought,
                            }, source="continuous_loop")
                    except Exception as e:
                        logger.debug(f"Agent '{agent.name}' think phase: {e}")

        emit(EventType.THOUGHT_STREAM, {
            "cycle": self._cycle_count,
            "phase": "think",
        }, source="continuous_loop")

    async def _plan_phase(self):
        self._current_phase = LoopPhase.PLAN

        now = time.time()
        idle = self._runtime.get("is_idle", False)
        if idle and (now - self._last_proactive_check) > self._proactive_interval:
            self._last_proactive_check = now
            emit(EventType.PROACTIVE_SUGGESTION, {
                "cycle": self._cycle_count,
                "idle_seconds": self._runtime.get("idle_seconds", 0),
            }, source="continuous_loop")

        emit(EventType.PLAN_CREATED, {
            "cycle": self._cycle_count,
            "phase": "plan",
            "has_proactive": idle,
        }, source="continuous_loop")

    async def _execute_phase(self):
        self._current_phase = LoopPhase.EXECUTE

        if self._orchestrator:
            for agent in self._orchestrator._agents.values():
                agent_context = self._agent_contexts.get(agent.name)
                if agent_context and agent.status == AgentStatus.RUNNING:
                    try:
                        if hasattr(agent, 'act'):
                            result = await agent.act(agent_context)
                            if result:
                                emit(EventType.AGENT_ACTION, {
                                    "agent": agent.name,
                                    "result": str(result)[:200],
                                }, source="continuous_loop")
                    except Exception as e:
                        logger.error(f"Agent '{agent.name}' execute phase failed: {e}")

        emit(EventType.AUTOMATION_STARTED if self._cycle_count > 0 else EventType.AUTOMATION_FINISHED, {
            "cycle": self._cycle_count,
            "phase": "execute",
        }, source="continuous_loop")

    async def _reflect_phase(self):
        self._current_phase = LoopPhase.REFLECT

        if self._orchestrator:
            reflection = self._orchestrator.get_agent("reflection")
            if reflection:
                try:
                    context = reflection._build_context()
                    thought = await reflection.think(context)
                    if thought:
                        await reflection.act(thought)
                        emit(EventType.AGENT_REFLECTION, {
                            "agent": "reflection",
                            "insights": thought,
                        }, source="continuous_loop")
                except Exception as e:
                    logger.debug(f"Reflection phase: {e}")

        emit(EventType.REFLECTION_COMPLETE, {
            "cycle": self._cycle_count,
            "phase": "reflect",
            "cycle_time_ms": round(self._last_cycle_time * 1000),
        }, source="continuous_loop")

    async def _learn_phase(self):
        self._current_phase = LoopPhase.LEARN

        emit(EventType.PERFORMANCE_EVALUATION, {
            "cycle": self._cycle_count,
            "avg_cycle_time_ms": round(sum(self._cycle_times[-10:]) / max(len(self._cycle_times[-10:]), 1) * 1000),
            "total_cycles": self._cycle_count,
            "agents_active": self._runtime.get("agents_active", []),
        }, source="continuous_loop")

    def get_stats(self) -> dict:
        avg_time = sum(self._cycle_times[-20:]) / max(len(self._cycle_times[-20:]), 1) if self._cycle_times else 0
        return {
            "cycles": self._cycle_count,
            "current_phase": self._current_phase.value,
            "avg_cycle_time_ms": round(avg_time * 1000),
            "last_cycle_time_ms": round(self._last_cycle_time * 1000),
            "is_running": self._running,
            "has_orchestrator": self._orchestrator is not None,
        }

    def __repr__(self):
        return f"ContinuousLoop(cycles={self._cycle_count}, phase={self._current_phase.value})"
