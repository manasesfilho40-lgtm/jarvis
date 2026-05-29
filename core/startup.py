import asyncio
import logging

logger = logging.getLogger("startup")

_plugins_loaded = False
_plugin_manager = None


def get_plugin_manager():
    global _plugin_manager
    if _plugin_manager is None:
        from plugins.plugin_manager import PluginManager
        _plugin_manager = PluginManager(plugin_dirs=[])
    return _plugin_manager


async def load_plugins():
    global _plugins_loaded
    if _plugins_loaded:
        return 0
    pm = get_plugin_manager()
    import os
    from pathlib import Path
    from core.utils import BASE_DIR
    plugin_dir = str(BASE_DIR / "plugins")
    if os.path.isdir(plugin_dir):
        count = await pm.discover_and_load([plugin_dir])
        _plugins_loaded = True
        logger.info(f"Loaded {count} plugins from {plugin_dir}")
        return count
    logger.warning(f"Plugin directory not found: {plugin_dir}")
    return 0


def init_event_bus(ui=None):
    from core.event_bus import get_bus, EventType
    bus = get_bus()
    if ui:
        bus.subscribe(EventType.UI_LOG_MESSAGE, lambda event: _ui_log_handler(ui, event))
        bus.subscribe(EventType.UI_STATE_CHANGED, lambda event: _ui_state_handler(ui, event))
    return bus


def _ui_log_handler(ui, event):
    try:
        data = event.data
        text = data if isinstance(data, str) else data.get("message", str(data))
        ui.write_log(text)
    except Exception:
        pass


def _ui_state_handler(ui, event):
    try:
        data = event.data
        state = data if isinstance(data, str) else data.get("state", "")
        if state:
            ui.set_state(state.upper())
    except Exception:
        pass


async def shutdown_plugins():
    pm = get_plugin_manager()
    await pm.unload_all()


def get_plugin_tools():
    pm = get_plugin_manager()
    tools = {}
    for plugin in pm.get_enabled_plugins():
        try:
            name = plugin.manifest.name
        except AttributeError:
            continue
        for attr_name in dir(plugin):
            if attr_name.startswith("get_") or attr_name.startswith("send_") or attr_name.startswith("play_") or attr_name.startswith("toggle_") or attr_name.startswith("search_") or attr_name in ("search", "translate", "scrape_url", "extract_text", "execute_command", "format_output"):
                if not attr_name.startswith("_"):
                    tools[f"plugin_{name}_{attr_name}"] = (plugin, attr_name)
    return tools