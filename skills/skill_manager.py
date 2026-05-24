import asyncio
import importlib.util
import inspect
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Optional

from skills.skill_base import BaseSkill, SkillManifest

logger = logging.getLogger("skill_manager")


class SkillManager:
    def __init__(self):
        self._skills: dict[str, BaseSkill] = {}
        self._skill_dirs: list[str] = []
        self._hook_registry: dict[str, list[tuple[str, Callable]]] = {}
        self._tool_registry: dict[str, str] = {}
        self._loaded = False

    async def discover(self, directories: list[str]) -> int:
        self._skill_dirs.extend(directories)
        count = 0
        for skill_dir in self._skill_dirs:
            path = Path(skill_dir)
            if not path.exists():
                logger.warning(f"Skill directory '{skill_dir}' not found")
                continue
            for item in path.iterdir():
                if item.is_dir():
                    manifest_file = item / "manifest.json"
                    main_file = item / "main.py"
                    if manifest_file.exists() and main_file.exists():
                        try:
                            skill = await self._load_skill(item)
                            if skill:
                                self._register_skill(skill)
                                count += 1
                        except Exception as e:
                            logger.error(f"Failed to load skill from '{item.name}': {e}")
                elif item.suffix == ".py" and item.stem not in ("__init__", "skill_base", "skill_manager"):
                    try:
                        skill = await self._load_skill_file(item)
                        if skill:
                            self._register_skill(skill)
                            count += 1
                    except Exception as e:
                        logger.error(f"Failed to load skill from '{item.name}': {e}")
        self._loaded = True
        logger.info(f"SkillManager: {count} skills loaded, {len(self._skills)} total")
        return count

    async def _load_skill(self, dirpath: Path) -> Optional[BaseSkill]:
        main_file = dirpath / "main.py"
        spec = importlib.util.spec_from_file_location(f"skills.{dirpath.name}", main_file)
        if not spec or not spec.loader:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        manifest_file = dirpath / "manifest.json"
        manifest = None
        if manifest_file.exists():
            data = json.loads(manifest_file.read_text(encoding="utf-8"))
            manifest = SkillManifest(**data)
        else:
            manifest = SkillManifest(name=dirpath.name)

        for _name, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and issubclass(obj, BaseSkill) and obj is not BaseSkill:
                instance = obj(manifest)
                await instance.on_load()
                return instance
        return None

    async def _load_skill_file(self, filepath: Path) -> Optional[BaseSkill]:
        spec = importlib.util.spec_from_file_location(filepath.stem, filepath)
        if not spec or not spec.loader:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        for _name, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and issubclass(obj, BaseSkill) and obj is not BaseSkill:
                manifest = getattr(obj, "manifest", None) or SkillManifest(name=filepath.stem)
                if isinstance(manifest, SkillManifest):
                    instance = obj(manifest)
                    await instance.on_load()
                    return instance
        return None

    def _register_skill(self, skill: BaseSkill):
        self._skills[skill.name] = skill

        for tool in skill.get_tools():
            tool_name = tool.get("name", "")
            if tool_name:
                self._tool_registry[tool_name] = skill.name

        hooks = skill.get_hooks()
        for hook_name, callback in hooks.items():
            if hook_name not in self._hook_registry:
                self._hook_registry[hook_name] = []
            self._hook_registry[hook_name].append((skill.name, callback))

        logger.info(f"Skill '{skill.name}' v{skill.manifest.version} registered")

    def get_skill(self, name: str) -> Optional[BaseSkill]:
        return self._skills.get(name)

    def get_skill_for_tool(self, tool_name: str) -> Optional[BaseSkill]:
        skill_name = self._tool_registry.get(tool_name)
        if skill_name:
            return self._skills.get(skill_name)
        return None

    async def execute_tool(self, tool_name: str, params: dict, context: dict = None) -> Any:
        skill = self.get_skill_for_tool(tool_name)
        if skill and skill.enabled:
            return await skill.execute(tool_name, params, context)
        raise ValueError(f"No skill found for tool '{tool_name}'")

    async def execute_hooks(self, hook_name: str, *args, **kwargs) -> list[Any]:
        results = []
        for skill_name, callback in self._hook_registry.get(hook_name, []):
            skill = self._skills.get(skill_name)
            if skill and skill.enabled:
                try:
                    result = callback(*args, **kwargs)
                    if hasattr(result, "__await__"):
                        result = await result
                    results.append(result)
                except Exception as e:
                    logger.error(f"Hook '{hook_name}' in skill '{skill_name}' failed: {e}")
        return results

    def list_skills(self) -> list[dict]:
        return [
            {
                "name": s.name,
                "version": s.manifest.version,
                "description": s.manifest.description,
                "enabled": s.enabled,
                "tools": len(s.get_tools()),
                "hooks": len(s.get_hooks()),
                "priority": s.manifest.priority,
            }
            for s in sorted(self._skills.values(), key=lambda x: -x.manifest.priority)
        ]

    def enable_skill(self, name: str):
        skill = self._skills.get(name)
        if skill:
            skill.enable()

    def disable_skill(self, name: str):
        skill = self._skills.get(name)
        if skill:
            skill.disable()

    async def reload_skill(self, name: str) -> bool:
        old_skill = self._skills.pop(name, None)
        if old_skill:
            await old_skill.on_unload()
        for skill_dir in self._skill_dirs:
            path = Path(skill_dir) / name
            if path.exists() and path.is_dir():
                skill = await self._load_skill(path)
                if skill:
                    self._register_skill(skill)
                    return True
            skill_file = Path(skill_dir) / f"{name}.py"
            if skill_file.exists():
                skill = await self._load_skill_file(skill_file)
                if skill:
                    self._register_skill(skill)
                    return True
        return False

    async def unload_all(self):
        for name, skill in list(self._skills.items()):
            try:
                await skill.on_unload()
            except Exception as e:
                logger.error(f"Error unloading skill '{name}': {e}")
        self._skills.clear()
        self._hook_registry.clear()
        self._tool_registry.clear()
        logger.info("All skills unloaded")


_skill_manager_instance = None


def get_skill_manager() -> SkillManager:
    global _skill_manager_instance
    if _skill_manager_instance is None:
        _skill_manager_instance = SkillManager()
    return _skill_manager_instance
