import asyncio
import inspect
import logging
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger("event_bus")


class EventPriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class EventType(str, Enum):
    # Voice events
    VOICE_INPUT = "voice_input"
    VOICE_OUTPUT = "voice_output"
    VOICE_COMMAND = "voice_command"
    WAKE_WORD = "wake_word"
    SILENCE_DETECTED = "silence_detected"

    # Vision events
    SCREEN_CHANGE = "screen_change"
    SCREENSHOT_TAKEN = "screenshot_taken"
    APP_DETECTED = "app_detected"
    UI_ELEMENT_DETECTED = "ui_element_detected"
    OCR_RESULT = "ocr_result"

    # Browser events
    BROWSER_OPENED = "browser_opened"
    BROWSER_NAVIGATED = "browser_navigated"
    BROWSER_CLOSED = "browser_closed"
    PAGE_LOADED = "page_loaded"
    FORM_DETECTED = "form_detected"

    # Task events
    TASK_CREATED = "task_created"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_CANCELLED = "task_cancelled"

    # Plan events
    PLAN_CREATED = "plan_created"
    PLAN_STEP_STARTED = "plan_step_started"
    PLAN_STEP_COMPLETED = "plan_step_completed"
    PLAN_STEP_FAILED = "plan_step_failed"
    PLAN_COMPLETED = "plan_completed"
    PLAN_FAILED = "plan_failed"

    # Memory events
    MEMORY_SAVED = "memory_saved"
    MEMORY_RETRIEVED = "memory_retrieved"
    MEMORY_CLEARED = "memory_cleared"
    MEMORY_COMPRESSED = "memory_compressed"

    # Automation events
    APP_OPENED = "app_opened"
    APP_CLOSED = "app_closed"
    AUTOMATION_STARTED = "automation_started"
    AUTOMATION_FINISHED = "automation_finished"
    AUTOMATION_FAILED = "automation_failed"
    MOUSE_MOVED = "mouse_moved"
    KEYBOARD_INPUT = "keyboard_input"
    FILE_CHANGED = "file_changed"

    # System events
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"
    SYSTEM_ERROR = "system_error"
    SYSTEM_WARNING = "system_warning"
    SYSTEM_HEALTH_CHECK = "system_health_check"
    MODE_CHANGED = "mode_changed"

    # Agent events
    AGENT_THOUGHT = "agent_thought"
    AGENT_ACTION = "agent_action"
    AGENT_OBSERVATION = "agent_observation"
    AGENT_REFLECTION = "agent_reflection"
    AGENT_REGISTERED = "agent_registered"
    AGENT_DEREGISTERED = "agent_deregistered"
    AGENT_ERROR = "agent_error"

    # User events
    USER_INPUT = "user_input"
    USER_ACTIVITY = "user_activity"
    USER_IDLE = "user_idle"
    USER_BUSY = "user_busy"

    # Security events
    COMMAND_VALIDATED = "command_validated"
    COMMAND_REJECTED = "command_rejected"
    DANGEROUS_ACTION = "dangerous_action"
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_DENIED = "permission_denied"

    # Plugin events
    PLUGIN_LOADED = "plugin_loaded"
    PLUGIN_UNLOADED = "plugin_unloaded"
    PLUGIN_ERROR = "plugin_error"

    # UI events
    UI_STATE_CHANGED = "ui_state_changed"
    UI_LOG_MESSAGE = "ui_log_message"
    UI_NOTIFICATION = "ui_notification"
    HUD_UPDATE = "hud_update"
    THOUGHT_STREAM = "thought_stream"

    # Observation events
    OBSERVER_CYCLE = "observer_cycle"
    CONTEXT_CHANGED = "context_changed"
    SITUATION_AWARE = "situation_aware"
    PROACTIVE_SUGGESTION = "proactive_suggestion"

    # Reflection events
    REFLECTION_COMPLETE = "reflection_complete"
    SELF_CRITIQUE = "self_critique"
    IMPROVEMENT_PROPOSED = "improvement_proposed"
    PERFORMANCE_EVALUATION = "performance_evaluation"

    # Error events
    ERROR_DETECTED = "error_detected"
    ERROR_RECOVERED = "error_recovered"
    ERROR_UNRECOVERABLE = "error_unrecoverable"


@dataclass
class Event:
    type: EventType
    data: Any = None
    source: str = ""
    priority: EventPriority = EventPriority.NORMAL
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    metadata: dict = field(default_factory=dict)

    def __repr__(self):
        return f"Event({self.type.value}, src={self.source}, id={self.event_id})"


EventHandler = Callable[[Event], Optional[Coroutine[Any, Any, None]]]


class EventBus:
    def __init__(self, max_workers: int = 4):
        self._handlers: dict[EventType, list[tuple[EventHandler, int, str]]] = defaultdict(list)
        self._wildcard_handlers: list[tuple[EventHandler, int, str]] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread_pool = ThreadPoolExecutor(max_workers=max_workers)
        self._history: list[Event] = []
        self._max_history = 1000
        self._stats: defaultdict[str, int] = defaultdict(int)
        self._logger = logging.getLogger("event_bus")

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_event_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    @loop.setter
    def loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def subscribe(self, event_type: EventType, handler: EventHandler, priority: int = 0, source: str = ""):
        self._handlers[event_type].append((handler, priority, source))
        self._handlers[event_type].sort(key=lambda x: -x[1])

    def subscribe_wildcard(self, handler: EventHandler, priority: int = 0, source: str = ""):
        self._wildcard_handlers.append((handler, priority, source))
        self._wildcard_handlers.sort(key=lambda x: -x[1])

    def unsubscribe(self, event_type: EventType, handler: EventHandler):
        self._handlers[event_type] = [(h, p, s) for h, p, s in self._handlers[event_type] if h != handler]
        if not self._handlers[event_type]:
            del self._handlers[event_type]

    def emit(self, event_type: EventType, data: Any = None, source: str = "", priority: EventPriority = EventPriority.NORMAL, metadata: dict | None = None) -> Event:
        event = Event(
            type=event_type,
            data=data,
            source=source,
            priority=priority,
            metadata=metadata or {},
        )
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        self._stats[event_type.value] += 1

        all_handlers = list(self._handlers.get(event_type, [])) + self._wildcard_handlers

        for handler, prio, src in all_handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    try:
                        loop = self.loop
                        if loop.is_running():
                            asyncio.run_coroutine_threadsafe(handler(event), loop)
                        else:
                            loop.run_until_complete(handler(event))
                    except RuntimeError:
                        self._thread_pool.submit(self._run_async_sync, handler, event)
                else:
                    handler(event)
            except Exception as e:
                self._logger.error(f"Handler for {event_type.value} failed: {e}")

        return event

    def emit_sync(self, event_type: EventType, data: Any = None, source: str = "", priority: EventPriority = EventPriority.NORMAL) -> Event:
        return self.emit(event_type, data, source, priority)

    async def emit_async(self, event_type: EventType, data: Any = None, source: str = "", priority: EventPriority = EventPriority.NORMAL) -> Event:
        event = Event(type=event_type, data=data, source=source, priority=priority)
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        self._stats[event_type.value] += 1

        all_handlers = list(self._handlers.get(event_type, [])) + self._wildcard_handlers

        for handler, prio, src in all_handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                self._logger.error(f"Handler for {event_type.value} failed: {e}")

        return event

    def _run_async_sync(self, handler, event):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(handler(event))
            loop.close()
        except Exception as e:
            self._logger.error(f"Async handler wrapper failed: {e}")

    def on(self, event_type: EventType):
        def decorator(func):
            self.subscribe(event_type, func)
            return func
        return decorator

    def once(self, event_type: EventType):
        def wrapper(handler):
            def _once_wrapper(event):
                self.unsubscribe(event_type, _once_wrapper)
                return handler(event)
            self.subscribe(event_type, _once_wrapper)
            return handler
        return wrapper

    def clear(self):
        self._handlers.clear()
        self._wildcard_handlers.clear()
        self._history.clear()

    def get_history(self, event_type: Optional[EventType] = None, limit: int = 50) -> list[Event]:
        if event_type:
            filtered = [e for e in self._history if e.type == event_type]
        else:
            filtered = list(self._history)
        return filtered[-limit:]

    def get_stats(self) -> dict:
        return dict(self._stats)

    def wait_for(self, event_type: EventType, timeout: float = 30.0) -> Optional[Event]:
        result = []
        event = threading.Event()

        def handler(evt):
            result.append(evt)
            event.set()

        self.subscribe(event_type, handler, priority=999)
        event.wait(timeout=timeout)
        self.unsubscribe(event_type, handler)
        return result[0] if result else None

    async def wait_for_async(self, event_type: EventType, timeout: float = 30.0) -> Optional[Event]:
        future = self.loop.create_future()

        def handler(evt):
            if not future.done():
                future.set_result(evt)

        self.subscribe(event_type, handler, priority=999)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            self.unsubscribe(event_type, handler)

    def get_subscriber_count(self, event_type: Optional[EventType] = None) -> int:
        if event_type:
            return len(self._handlers.get(event_type, []))
        return sum(len(h) for h in self._handlers.values())

    def __repr__(self):
        return f"EventBus(events={len(self._history)}, subscribers={self.get_subscriber_count()})"


import threading


_event_bus_instance = None
_bus_lock = threading.Lock()


def get_bus() -> EventBus:
    global _event_bus_instance
    with _bus_lock:
        if _event_bus_instance is None:
            _event_bus_instance = EventBus()
        return _event_bus_instance


def emit(event_type: EventType, data: Any = None, source: str = "", priority: EventPriority = EventPriority.NORMAL):
    return get_bus().emit(event_type, data, source, priority)

def emit_sync(event_type: EventType, data: Any = None, source: str = ""):
    return emit(event_type, data, source)

async def emit_async(event_type: EventType, data: Any = None, source: str = ""):
    return await get_bus().emit_async(event_type, data, source)

def on(event_type: EventType):
    return get_bus().on(event_type)

def subscribe(event_type: EventType, handler: EventHandler, priority: int = 0, source: str = ""):
    get_bus().subscribe(event_type, handler, priority, source)
