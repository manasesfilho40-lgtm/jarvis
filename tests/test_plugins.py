import sys
import os
import asyncio
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from plugins.plugin_base import BasePlugin, PluginManifest, HookType, PluginPriority


class TestPluginBase:
    def test_plugin_manifest_creation(self, base_plugin):
        assert base_plugin.name == "test_plugin"
        assert base_plugin.version == "1.0.0"
        assert base_plugin.description == "Test plugin for unit tests"
        assert base_plugin.priority == PluginPriority.NORMAL

    def test_plugin_manifest_defaults(self):
        m = PluginManifest(name="minimal")
        assert m.version == "1.0.0"
        assert m.description == ""
        assert m.author == ""
        assert m.dependencies == []
        assert m.priority == PluginPriority.NORMAL
        assert m.icon == ""
        assert m.tags == []

    def test_plugin_priority_values(self):
        assert PluginPriority.LOWEST.value == 0
        assert PluginPriority.LOW.value == 25
        assert PluginPriority.NORMAL.value == 50
        assert PluginPriority.HIGH.value == 75
        assert PluginPriority.HIGHEST.value == 100


class TestHookType:
    def test_hook_type_values(self):
        assert HookType.BEFORE_OBSERVE.value == "before_observe"
        assert HookType.ON_SYSTEM_STARTUP.value == "on_system_startup"
        assert HookType.ON_SYSTEM_SHUTDOWN.value == "on_system_shutdown"
        assert HookType.ON_MESSAGE.value == "on_message"
        assert HookType.ON_VOICE_INPUT.value == "on_voice_input"
        assert HookType.ON_EVENT.value == "on_event"
        assert len(HookType) == 16  # Total hook types


@pytest.mark.asyncio
class TestPluginLoading:
    async def test_all_plugins_load(self, loaded_plugins):
        pm = loaded_plugins
        names = sorted([p.manifest.name for p in pm.get_all_plugins()])
        expected = [
            "cli", "discord", "docker", "email", "github", "notion", "obs",
            "spotify", "steam", "system_monitor", "telegram", "translator",
            "vscode", "weather", "web_scraper", "whatsapp", "youtube",
        ]
        assert names == expected, f"Missing plugins: {set(expected) - set(names)}"

    async def test_plugin_count(self, loaded_plugins):
        assert loaded_plugins.plugin_count == 17

    async def test_all_plugins_enabled(self, loaded_plugins):
        for p in loaded_plugins.get_all_plugins():
            assert p.enabled, f"Plugin {p.manifest.name} is not enabled"

    async def test_plugin_has_manifest(self, loaded_plugins):
        for p in loaded_plugins.get_all_plugins():
            assert p.manifest.name, f"Plugin missing name"
            assert p.manifest.version, f"Plugin {p.manifest.name} missing version"

    async def test_get_plugin_by_name(self, loaded_plugins):
        for name in ["cli", "translator", "weather", "youtube"]:
            p = loaded_plugins.get_plugin(name)
            assert p is not None, f"Plugin '{name}' not found"
            assert p.manifest.name == name

    async def test_get_nonexistent_plugin(self, loaded_plugins):
        p = loaded_plugins.get_plugin("nonexistent_plugin")
        assert p is None


@pytest.mark.asyncio
class TestCLIPlugin:
    async def test_cli_basic_commands(self, loaded_plugins):
        cli = loaded_plugins.get_plugin("cli")
        assert cli is not None

        help_result = await cli.execute_command("help")
        assert "J.A.R.V.I.S" in help_result

        history_result = await cli.execute_command("history")
        assert "No commands" in history_result or "help" in history_result

    async def test_cli_format_output(self, loaded_plugins):
        cli = loaded_plugins.get_plugin("cli")
        dict_out = await cli.format_output({"key": "value"})
        assert "key" in dict_out
        assert "value" in dict_out

        list_out = await cli.format_output(["a", "b", "c"])
        assert "a" in list_out
        assert "2." in list_out


@pytest.mark.asyncio
class TestTranslatorPlugin:
    async def test_translate(self, loaded_plugins):
        tr = loaded_plugins.get_plugin("translator")
        assert tr is not None

        result = await tr.translate("Hello world", target_lang="pt")
        assert result is not None
        assert len(result) > 0

    async def test_detect_language(self, loaded_plugins):
        tr = loaded_plugins.get_plugin("translator")
        detected = await tr.detect_language("Bonjour le monde")
        assert detected == "fr"

    async def test_supported_languages(self, loaded_plugins):
        tr = loaded_plugins.get_plugin("translator")
        langs = await tr.get_supported_languages()
        assert "pt" in langs
        assert "en" in langs
        assert len(langs) >= 10


@pytest.mark.asyncio
class TestSystemMonitorPlugin:
    async def test_system_info(self, loaded_plugins):
        sm = loaded_plugins.get_plugin("system_monitor")
        assert sm is not None

        info = await sm.get_system_info()
        assert "hostname" in info
        assert "system" in info
        assert info["system"] in ("Windows", "Linux", "Darwin")

    async def test_cpu_info(self, loaded_plugins):
        sm = loaded_plugins.get_plugin("system_monitor")
        cpu = await sm.get_cpu_info()
        assert "percent" in cpu
        assert "count" in cpu
        assert cpu["count"] >= 1

    async def test_memory_info(self, loaded_plugins):
        sm = loaded_plugins.get_plugin("system_monitor")
        mem = await sm.get_memory_info()
        assert "total_gb" in mem
        assert mem["total_gb"] > 0
        assert "percent" in mem


@pytest.mark.asyncio
class TestWeatherPlugin:
    async def test_geocoding(self, loaded_plugins):
        we = loaded_plugins.get_plugin("weather")
        assert we is not None

        coords = await we.get_coordinates("Sao Paulo")
        assert coords is not None
        assert len(coords) == 4
        lat, lon = coords[0], coords[1]
        assert -90 <= lat <= 90
        assert -180 <= lon <= 180

    async def test_geocoding_invalid_city(self, loaded_plugins):
        we = loaded_plugins.get_plugin("weather")
        coords = await we.get_coordinates("xyzxyzxyzxyz123")
        assert coords is None


@pytest.mark.asyncio
class TestYouTubePlugin:
    async def test_extract_video_id(self, loaded_plugins):
        yt = loaded_plugins.get_plugin("youtube")
        assert yt is not None

        video_id = yt._extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert video_id == "dQw4w9WgXcQ"

        video_id = yt._extract_video_id("dQw4w9WgXcQ")
        assert video_id == "dQw4w9WgXcQ"

        video_id = yt._extract_video_id("https://youtu.be/dQw4w9WgXcQ")
        assert video_id == "dQw4w9WgXcQ"

        video_id = yt._extract_video_id("invalid")
        assert video_id is None


@pytest.mark.asyncio
class TestWebScraperPlugin:
    async def test_scrape_invalid_url(self, loaded_plugins):
        ws = loaded_plugins.get_plugin("web_scraper")
        assert ws is not None

        result = await ws.scrape_url("https://invalid.url.xyz999")
        assert result is None


@pytest.mark.asyncio
class TestPluginManager:
    async def test_get_enabled_plugins(self, loaded_plugins):
        pm = loaded_plugins
        enabled = pm.get_enabled_plugins()
        assert len(enabled) == 17  # All plugins enabled

    async def test_plugin_manager_loaded_property(self, loaded_plugins):
        pm = loaded_plugins
        assert pm.loaded is True

    async def test_hook_registry_exists(self, loaded_plugins):
        pm = loaded_plugins
        for hook_type in HookType:
            assert hook_type in pm._hook_registry


@pytest.mark.asyncio
class TestEventBus:
    async def test_event_bus_exists(self):
        from core.event_bus import get_bus, EventType
        bus = get_bus()
        assert bus is not None

        assert EventType.SYSTEM_STARTUP is not None
        assert EventType.USER_INPUT is not None
        assert EventType.UI_LOG_MESSAGE is not None


class TestStartupModule:
    def test_get_plugin_tools(self):
        from core.startup import get_plugin_tools
        tools = get_plugin_tools()
        assert len(tools) > 0
        assert any("plugin_" in k for k in tools.keys())


@pytest.mark.asyncio
class TestEmailPlugin:
    async def test_email_plugin_loaded(self, loaded_plugins):
        email = loaded_plugins.get_plugin("email")
        assert email is not None
        assert email.manifest.name == "email"

    async def test_email_read_inbox_no_creds(self, loaded_plugins):
        email = loaded_plugins.get_plugin("email")
        result = await email.read_inbox(limit=1)
        assert result == [] or result is None or "error" in str(result).lower() or "config" in str(result).lower()


@pytest.mark.asyncio
class TestGitHubPlugin:
    async def test_github_plugin_loaded(self, loaded_plugins):
        gh = loaded_plugins.get_plugin("github")
        assert gh is not None
        assert gh.manifest.name == "github"


@pytest.mark.asyncio
class TestSteamPlugin:
    async def test_steam_plugin_loaded(self, loaded_plugins):
        steam = loaded_plugins.get_plugin("steam")
        assert steam is not None
        assert steam.manifest.name == "steam"


@pytest.mark.asyncio
class TestDockerPlugin:
    async def test_docker_plugin_loaded(self, loaded_plugins):
        docker = loaded_plugins.get_plugin("docker")
        assert docker is not None
        assert docker.manifest.name == "docker"


@pytest.mark.asyncio
class TestWebScraperPluginExtended:
    async def test_scrape_extract_text_invalid(self, loaded_plugins):
        ws = loaded_plugins.get_plugin("web_scraper")
        assert ws is not None
        result = await ws.extract_text("https://invalid.url.xyz999")
        assert result is None


class TestPluginManifestBase:
    def test_manifest_name(self, base_plugin):
        assert base_plugin.name == "test_plugin"

    def test_manifest_version(self, base_plugin):
        assert base_plugin.version == "1.0.0"

    def test_manifest_description(self, base_plugin):
        assert base_plugin.description == "Test plugin for unit tests"