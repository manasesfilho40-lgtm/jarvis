import asyncio
import importlib
import importlib.util
import inspect
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

from plugins.plugin_base import BasePlugin, HookType, PluginManifest

logger = logging.getLogger("plugin_manager")


class PluginManager:
    def __init__(self, plugin_dirs: list[str] = None):
        self._plugins: dict[str, BasePlugin] = {}
        self._plugin_dirs = plugin_dirs or []
        self._hook_registry: dict[HookType, list[tuple[str, callable]]] = {
            hook_type: [] for hook_type in HookType
        }
        self._loaded = False
        self._global_config: dict = self._load_global_config()

    def _load_global_config(self) -> dict:
        config = {}
        try:
            from core.utils import BASE_DIR
            api_keys_path = BASE_DIR / "config" / "api_keys.json"
            if api_keys_path.exists():
                import json
                with open(api_keys_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            model_settings_path = BASE_DIR / "config" / "model_settings.json"
            if model_settings_path.exists():
                import json
                with open(model_settings_path, "r", encoding="utf-8") as f:
                    config.update(json.load(f))
        except Exception:
            pass
        return config

    async def discover_and_load(self, plugin_dirs: list[str] = None) -> int:
        if plugin_dirs:
            self._plugin_dirs.extend(plugin_dirs)

        count = 0
        for plugin_dir in self._plugin_dirs:
            plugin_path = Path(plugin_dir)
            if not plugin_path.exists():
                logger.warning(f"Plugin directory '{plugin_dir}' not found")
                continue

            for item in plugin_path.iterdir():
                if item.suffix == ".py" and item.stem not in ("__init__", "plugin_base", "plugin_manager"):
                    try:
                        plugin = await self._load_plugin_from_file(item)
                        if plugin:
                            self._register(plugin)
                            count += 1
                    except Exception as e:
                        logger.error(f"Failed to load plugin from '{item.name}': {e}")

                elif item.is_dir() and (item / "manifest.json").exists():
                    try:
                        plugin = await self._load_plugin_from_dir(item)
                        if plugin:
                            self._register(plugin)
                            count += 1
                    except Exception as e:
                        logger.error(f"Failed to load plugin from directory '{item.name}': {e}")

        self._loaded = True
        logger.info(f"Plugin manager: {count} plugins loaded")
        return count

    async def _load_plugin_from_file(self, filepath: Path) -> Optional[BasePlugin]:
        spec = importlib.util.spec_from_file_location(filepath.stem, filepath)
        if not spec or not spec.loader:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        for _name, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and issubclass(obj, BasePlugin) and obj is not BasePlugin:
                manifest = getattr(obj, "manifest", None) or getattr(module, "manifest", None) or PluginManifest(name=filepath.stem)
                if isinstance(manifest, PluginManifest):
                    instance = obj(manifest)
                    plugin_config = self._get_plugin_config(manifest.name)
                    instance.set_config(plugin_config)
                    await instance.on_load()
                    return instance

        logger.debug(f"No BasePlugin subclass found in '{filepath.name}'")
        return None

    async def _load_plugin_from_dir(self, dirpath: Path) -> Optional[BasePlugin]:
        main_file = dirpath / "main.py"
        if not main_file.exists():
            logger.warning(f"Plugin directory '{dirpath.name}' has no main.py")
            return None

        spec = importlib.util.spec_from_file_location(dirpath.name, main_file)
        if not spec or not spec.loader:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        for _name, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and issubclass(obj, BasePlugin) and obj is not BasePlugin:
                manifest_file = dirpath / "manifest.json"
                manifest = None
                if manifest_file.exists():
                    data = json.loads(manifest_file.read_text(encoding="utf-8"))
                    manifest = PluginManifest(**data)
                else:
                    manifest = getattr(obj, "manifest", PluginManifest(name=dirpath.name))

                instance = obj(manifest)
                plugin_config = self._get_plugin_config(manifest.name)
                instance.set_config(plugin_config)
                await instance.on_load()
                return instance

        return None

    def _get_plugin_config(self, plugin_name: str) -> dict:
        plugin_prefixes = {
            "discord": ["discord_token", "discord_channel_id"],
            "telegram": ["telegram_token", "telegram_chat_id"],
            "github": ["github_token"],
            "spotify": ["spotify_client_id", "spotify_client_secret"],
            "email": ["email_address", "email_password", "imap_server", "smtp_server"],
            "notion": ["notion_token"],
            "weather": ["default_city", "openweather_key"],
            "system_monitor": ["alert_threshold_cpu", "alert_threshold_memory"],
            "youtube": [],
            "translator": ["default_target_lang", "default_source_lang"],
            "web_scraper": [],
            "cli": ["max_history", "prompt"],
        }
        config = dict(self._global_config)
        prefixes = plugin_prefixes.get(plugin_name, [plugin_name])
        plugin_specific = {}
        for prefix in prefixes:
            for key, value in config.items():
                if key.startswith(prefix) or key == prefix:
                    plugin_specific[key] = value
        return plugin_specific if plugin_specific else config

    def _register(self, plugin: BasePlugin):
        self._plugins[plugin.manifest.name] = plugin
        for hook_type in HookType:
            for callback in plugin.get_hooks(hook_type):
                self._hook_registry[hook_type].append((plugin.manifest.name, callback))

        logger.info(f"Plugin '{plugin.manifest.name}' registered with {sum(len(v) for v in plugin._hooks.values())} hooks")

    async def unload_all(self):
        for name, plugin in list(self._plugins.items()):
            try:
                await plugin.on_unload()
                plugin.disable()
            except Exception as e:
                logger.error(f"Error unloading plugin '{name}': {e}")
        self._plugins.clear()
        self._hook_registry = {hook_type: [] for hook_type in HookType}
        logger.info("All plugins unloaded")

    async def execute_hooks(self, hook_type: HookType, *args, **kwargs) -> dict[str, list[Any]]:
        results = {}
        for plugin_name, callback in self._hook_registry.get(hook_type, []):
            plugin = self._plugins.get(plugin_name)
            if not plugin or not plugin.enabled:
                continue
            try:
                result = callback(*args, **kwargs)
                if hasattr(result, "__await__"):
                    result = await result
                if plugin_name not in results:
                    results[plugin_name] = []
                results[plugin_name].append(result)
            except Exception as e:
                logger.error(f"Hook '{hook_type.value}' in plugin '{plugin_name}' failed: {e}")
        return results

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        return self._plugins.get(name)

    def get_all_plugins(self) -> list[BasePlugin]:
        return list(self._plugins.values())

    def get_enabled_plugins(self) -> list[BasePlugin]:
        return [p for p in self._plugins.values() if p.enabled]

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def plugin_count(self) -> int:
        return len(self._plugins)


_plugin_manager_instance = None


def get_plugin_manager() -> PluginManager:
    global _plugin_manager_instance
    if _plugin_manager_instance is None:
        _plugin_manager_instance = PluginManager()
    return _plugin_manager_instance
