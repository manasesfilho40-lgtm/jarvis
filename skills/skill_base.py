import importlib.util
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("skill_base")


@dataclass
class SkillManifest:
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    dependencies: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)
    priority: int = 0
    requires_confirmation: bool = False
    tags: list[str] = field(default_factory=list)
    icon: str = ""


class BaseSkill:
    def __init__(self, manifest: SkillManifest):
        self.manifest = manifest
        self._enabled = True
        self._logger = logging.getLogger(f"skill.{manifest.name}")

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self):
        self._enabled = True
        self._logger.info(f"Skill '{self.name}' enabled")

    def disable(self):
        self._enabled = False
        self._logger.info(f"Skill '{self.name}' disabled")

    async def on_load(self):
        pass

    async def on_unload(self):
        pass

    async def execute(self, action: str, params: dict, context: dict = None) -> Any:
        raise NotImplementedError(f"Skill '{self.name}' does not implement execute()")

    def get_tools(self) -> list[dict]:
        return []

    def get_hooks(self) -> dict[str, Callable]:
        return {}

    def __repr__(self):
        return f"Skill(name={self.name}, v={self.manifest.version}, enabled={self._enabled})"
