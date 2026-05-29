import sys
import os
import asyncio
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from plugins.plugin_base import BasePlugin, PluginManifest, HookType, PluginPriority


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def plugin_manager():
    from core.startup import get_plugin_manager
    pm = get_plugin_manager()
    return pm


@pytest.fixture(scope="session")
async def loaded_plugins(plugin_manager):
    from core.startup import load_plugins
    count = await load_plugins()
    return plugin_manager


@pytest.fixture
def base_plugin():
    manifest = PluginManifest(
        name="test_plugin",
        version="1.0.0",
        description="Test plugin for unit tests",
    )
    return manifest