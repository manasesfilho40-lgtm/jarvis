import asyncio
import logging
from typing import Any, Optional

from plugins.plugin_base import BasePlugin, PluginManifest, HookType

logger = logging.getLogger("plugin_obs")

try:
    import obsws_python as obs
    HAS_OBS = True
except ImportError:
    HAS_OBS = False


class OBSPlugin(BasePlugin):
    def __init__(self, manifest: Optional[PluginManifest] = None):
        if manifest is None:
            manifest = PluginManifest(
                name="obs",
                version="1.0.0",
                description="OBS Studio integration - scenes, recording, streaming",
            )
        super().__init__(manifest)
        self._client: Optional[Any] = None
        self._host: str = "localhost"
        self._port: int = 4455
        self._password: str = ""

    async def on_load(self):
        self._host = self.config.get("obs_host", "localhost")
        self._port = int(self.config.get("obs_port", 4455))
        self._password = self.config.get("obs_password", "")
        if HAS_OBS:
            try:
                self._client = obs.ReqClient(
                    host=self._host,
                    port=self._port,
                    password=self._password,
                    timeout=3,
                )
                version = self._client.get_version()
                logger.info(f"OBS plugin loaded - connected to OBS v{version}")
            except Exception as e:
                logger.warning(f"OBS plugin loaded - could not connect: {e}")
                self._client = None
        else:
            logger.warning("OBS plugin loaded - obsws_python not installed. Install with: pip install obsws-python")

    async def on_unload(self):
        if self._client:
            try:
                self._client.disconnect()
            except Exception:
                pass
        logger.info("OBS plugin unloaded")

    def _ensure_client(self) -> bool:
        if self._client:
            try:
                self._client.get_version()
                return True
            except Exception:
                pass
        if HAS_OBS:
            try:
                self._client = obs.ReqClient(
                    host=self._host,
                    port=self._port,
                    password=self._password,
                    timeout=3,
                )
                return True
            except Exception as e:
                logger.error(f"Failed to connect to OBS: {e}")
        return False

    async def get_status(self) -> dict:
        if not self._ensure_client():
            return {"connected": False}
        try:
            status = self._client.get_record_status()
            stream_status = self._client.get_stream_status()
            scene = self._client.get_current_program_scene()
            return {
                "connected": True,
                "recording": status.output_active if hasattr(status, "output_active") else False,
                "recording_time": status.output_duration if hasattr(status, "output_duration") else 0,
                "streaming": stream_status.output_active if hasattr(stream_status, "output_active") else False,
                "current_scene": scene.current_program_scene_name if hasattr(scene, "current_program_scene_name") else "unknown",
            }
        except Exception as e:
            logger.error(f"Failed to get OBS status: {e}")
            return {"connected": False, "error": str(e)}

    async def start_recording(self) -> bool:
        if not self._ensure_client():
            return False
        try:
            self._client.start_record()
            logger.info("OBS recording started")
            return True
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            return False

    async def stop_recording(self) -> bool:
        if not self._ensure_client():
            return False
        try:
            self._client.stop_record()
            logger.info("OBS recording stopped")
            return True
        except Exception as e:
            logger.error(f"Failed to stop recording: {e}")
            return False

    async def toggle_recording(self) -> bool:
        status = await self.get_status()
        if status.get("recording"):
            return await self.stop_recording()
        else:
            return await self.start_recording()

    async def start_streaming(self) -> bool:
        if not self._ensure_client():
            return False
        try:
            self._client.start_stream()
            logger.info("OBS streaming started")
            return True
        except Exception as e:
            logger.error(f"Failed to start streaming: {e}")
            return False

    async def stop_streaming(self) -> bool:
        if not self._ensure_client():
            return False
        try:
            self._client.stop_stream()
            logger.info("OBS streaming stopped")
            return True
        except Exception as e:
            logger.error(f"Failed to stop streaming: {e}")
            return False

    async def switch_scene(self, scene_name: str) -> bool:
        if not self._ensure_client():
            return False
        try:
            self._client.set_current_program_scene(scene_name)
            logger.info(f"OBS switched to scene: {scene_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to switch scene: {e}")
            return False

    async def list_scenes(self) -> list[str]:
        if not self._ensure_client():
            return []
        try:
            scenes = self._client.get_scene_list()
            return [s["sceneName"] for s in scenes.scenes] if hasattr(scenes, "scenes") else []
        except Exception as e:
            logger.error(f"Failed to list scenes: {e}")
            return []

    async def set_source_visibility(self, source_name: str, visible: bool) -> bool:
        if not self._ensure_client():
            return False
        try:
            scene = self._client.get_current_program_scene()
            scene_name = scene.current_program_scene_name if hasattr(scene, "current_program_scene_name") else ""
            if not scene_name:
                return False
            self._client.set_scene_item_enabled(scene_name, source_name, visible)
            logger.info(f"OBS source '{source_name}' visibility set to {visible}")
            return True
        except Exception as e:
            logger.error(f"Failed to set source visibility: {e}")
            return False


manifest = PluginManifest(
    name="obs",
    version="1.0.0",
    description="OBS Studio integration - scenes, recording, streaming",
)
