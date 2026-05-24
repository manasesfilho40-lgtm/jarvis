import asyncio
import logging
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from core.event_bus import Event, EventBus, EventType, get_bus
from core.runtime import get_runtime

logger = logging.getLogger("agent_base")


class AgentStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    THINKING = "thinking"
    WAITING = "waiting"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class AgentMessage:
    type: str
    content: Any
    source: str = ""
    target: str = ""
    timestamp: float = field(default_factory=time.time)
    message_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def __repr__(self):
        return f"AgentMsg({self.type}, src={self.source}, dst={self.target})"


class BaseAgent(ABC):
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description or f"{name} agent"
        self.status = AgentStatus.IDLE
        self._bus: EventBus = get_bus()
        self._runtime = get_runtime()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._message_queue: list[AgentMessage] = []
        self._subscribed_events: list[EventType] = []
        self._stats = {"messages_processed": 0, "errors": 0, "total_runtime": 0.0}
        self._started_at: float = 0.0
        logger.info(f"Agent '{name}' created: {description}")

    @abstractmethod
    async def think(self, context: dict) -> Optional[dict]: ...

    @abstractmethod
    async def act(self, thought: dict) -> Any: ...

    async def observe(self, event: Event) -> Optional[dict]:
        return None

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
            self._started_at = time.time()
            self.status = AgentStatus.RUNNING
            self._thread = threading.Thread(target=self._run_loop, daemon=True, name=f"Agent-{self.name}")
            self._thread.start()

            for event_type in self._subscribed_events:
                self._bus.subscribe(event_type, self._on_event, source=self.name)

            self._bus.emit(EventType.AGENT_REGISTERED, {
                "name": self.name, "description": self.description,
            }, source=self.name)
            logger.info(f"Agent '{self.name}' started")

    def stop(self):
        with self._lock:
            self._running = False
            self.status = AgentStatus.STOPPED
            for event_type in self._subscribed_events:
                self._bus.unsubscribe(event_type, self._on_event)
            self._bus.emit(EventType.AGENT_DEREGISTERED, {"name": self.name}, source=self.name)
            logger.info(f"Agent '{self.name}' stopped")

    def _run_loop(self):
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._agent_loop())
        except Exception as e:
            logger.error(f"Agent '{self.name}' loop failed: {e}")
            self.status = AgentStatus.ERROR

    async def _agent_loop(self):
        while self._running:
            try:
                context = self._build_context()
                thought = await self.think(context)
                if thought:
                    result = await self.act(thought)
                    self._process_result(result)
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Agent '{self.name}' cycle error: {e}")
                self._stats["errors"] += 1
                self._bus.emit(EventType.AGENT_ERROR, {
                    "agent": self.name, "error": str(e),
                }, source=self.name)
                await asyncio.sleep(1)

    def _build_context(self) -> dict:
        return {
            "agent_name": self.name,
            "status": self.status.value,
            "runtime": self._runtime.get_system_context(),
            "messages_pending": len(self._message_queue),
        }

    def _process_result(self, result: Any):
        self._stats["messages_processed"] += 1

    def _on_event(self, event: Event):
        try:
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(self._handle_event(event), self._loop)
        except Exception as e:
            logger.error(f"Agent '{self.name}' event handler failed: {e}")

    async def _handle_event(self, event: Event):
        observation = await self.observe(event)
        if observation:
            msg = AgentMessage(
                type=f"event.{event.type.value}",
                content=observation,
                source=self.name,
            )
            self._message_queue.append(msg)

    def send_message(self, msg: AgentMessage):
        self._message_queue.append(msg)

    def get_message(self) -> Optional[AgentMessage]:
        if self._message_queue:
            return self._message_queue.pop(0)
        return None

    def get_stats(self) -> dict:
        stats = dict(self._stats)
        stats["uptime"] = time.time() - self._started_at if self._started_at else 0
        stats["status"] = self.status.value
        stats["queue_size"] = len(self._message_queue)
        return stats

    def subscribe_to(self, *event_types: EventType):
        self._subscribed_events.extend(event_types)

    def emit(self, event_type: EventType, data: Any = None):
        self._bus.emit(event_type, data, source=self.name)

    def log(self, msg: str, level: str = "info"):
        getattr(logger, level, logger.info)(f"[{self.name}] {msg}")

    def __repr__(self):
        return f"{self.__class__.__name__}(name={self.name}, status={self.status.value})"
