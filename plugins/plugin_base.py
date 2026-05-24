import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("plugin_base")


class PluginPriority(Enum):
    LOWEST = 0
    LOW = 25
    NORMAL = 50
    HIGH = 75
    HIGHEST = 100


@dataclass
class PluginManifest:
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    dependencies: list[str] = field(default_factory=list)
    priority: PluginPriority = PluginPriority.NORMAL
    icon: str = ""
    tags: list[str] = field(default_factory=list)


class HookType(Enum):
    BEFORE_OBSERVE = "before_observe"
    AFTER_OBSERVE = "after_observe"
    BEFORE_THINK = "before_think"
    AFTER_THINK = "after_think"
    BEFORE_EXECUTE = "before_execute"
    AFTER_EXECUTE = "after_execute"
    BEFORE_REFLECT = "before_reflect"
    AFTER_REFLECT = "after_reflect"
    ON_SYSTEM_STARTUP = "on_system_startup"
    ON_SYSTEM_SHUTDOWN = "on_system_shutdown"
    ON_EVENT = "on_event"
    ON_MESSAGE = "on_message"
    ON_VOICE_INPUT = "on_voice_input"
    ON_VOICE_OUTPUT = "on_voice_output"
    ON_VISION_CAPTURE = "on_vision_capture"
    ON_BROWSER_ACTION = "on_browser_action"


class BasePlugin(ABC):
    def __init__(self, manifest: PluginManifest):
        self.manifest = manifest
        self._enabled = True
        self._hooks: dict[HookType, list[callable]] = {}
        self._config: dict = {}
        logger.info(f"Plugin '{manifest.name}' v{manifest.version} initialized")

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def config(self) -> dict:
        return self._config

    def set_config(self, config: dict):
        self._config = config

    def enable(self):
        self._enabled = True
        logger.info(f"Plugin '{self.manifest.name}' enabled")

    def disable(self):
        self._enabled = False
        logger.info(f"Plugin '{self.manifest.name}' disabled")

    @abstractmethod
    async def on_load(self):
        pass

    @abstractmethod
    async def on_unload(self):
        pass

    def register_hook(self, hook_type: HookType, callback: callable):
        if hook_type not in self._hooks:
            self._hooks[hook_type] = []
        self._hooks[hook_type].append(callback)
        logger.debug(f"Plugin '{self.manifest.name}' registered hook '{hook_type.value}'")

    def get_hooks(self, hook_type: HookType) -> list[callable]:
        return self._hooks.get(hook_type, [])

    async def execute_hook(self, hook_type: HookType, *args, **kwargs) -> list[Any]:
        if not self._enabled:
            return []
        results = []
        for callback in self._hooks.get(hook_type, []):
            try:
                result = callback(*args, **kwargs)
                if hasattr(result, "__await__"):
                    result = await result
                results.append(result)
            except Exception as e:
                logger.error(f"Plugin '{self.manifest.name}' hook '{hook_type.value}' failed: {e}")
        return results
