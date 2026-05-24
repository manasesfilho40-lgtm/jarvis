import asyncio
import logging
from typing import Any, Optional

from plugins.plugin_base import BasePlugin, PluginManifest, HookType

logger = logging.getLogger("plugin_docker")

try:
    import docker
    from docker.errors import DockerException, NotFound, APIError
    HAS_DOCKER = True
except ImportError:
    HAS_DOCKER = False


class DockerPlugin(BasePlugin):
    def __init__(self, manifest: Optional[PluginManifest] = None):
        if manifest is None:
            manifest = PluginManifest(
                name="docker",
                version="1.0.0",
                description="Docker containers management - list, start, stop, logs, stats",
            )
        super().__init__(manifest)
        self._client: Any = None

    async def on_load(self):
        if not HAS_DOCKER:
            logger.warning("Docker plugin loaded - docker SDK not installed. Install with: pip install docker")
            return
        try:
            self._client = docker.from_env(timeout=10)
            self._client.ping()
            logger.info("Docker plugin loaded - connected to Docker daemon")
        except DockerException as e:
            logger.warning(f"Docker plugin loaded - could not connect: {e}")
            self._client = None

    async def on_unload(self):
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        logger.info("Docker plugin unloaded")

    @property
    def available(self) -> bool:
        return self._client is not None

    async def list_containers(self, all: bool = False) -> list[dict]:
        if not self._client:
            return []
        try:
            containers = self._client.containers.list(all=all)
            return [
                {
                    "id": c.short_id,
                    "name": c.name,
                    "image": c.image.tags[0] if c.image.tags else c.image.short_id,
                    "status": c.status,
                    "state": c.attrs.get("State", {}).get("Status", "unknown"),
                    "ports": list(c.attrs.get("NetworkSettings", {}).get("Ports", {}).keys()),
                    "created": c.attrs.get("Created", ""),
                }
                for c in containers
            ]
        except DockerException as e:
            logger.error(f"Failed to list containers: {e}")
            return []

    async def start_container(self, container_id: str) -> bool:
        if not self._client:
            return False
        try:
            container = self._client.containers.get(container_id)
            container.start()
            logger.info(f"Container started: {container_id}")
            return True
        except (NotFound, APIError) as e:
            logger.error(f"Failed to start container {container_id}: {e}")
            return False

    async def stop_container(self, container_id: str, timeout: int = 10) -> bool:
        if not self._client:
            return False
        try:
            container = self._client.containers.get(container_id)
            container.stop(timeout=timeout)
            logger.info(f"Container stopped: {container_id}")
            return True
        except (NotFound, APIError) as e:
            logger.error(f"Failed to stop container {container_id}: {e}")
            return False

    async def restart_container(self, container_id: str, timeout: int = 10) -> bool:
        if not self._client:
            return False
        try:
            container = self._client.containers.get(container_id)
            container.restart(timeout=timeout)
            logger.info(f"Container restarted: {container_id}")
            return True
        except (NotFound, APIError) as e:
            logger.error(f"Failed to restart container {container_id}: {e}")
            return False

    async def container_logs(self, container_id: str, tail: int = 50) -> str:
        if not self._client:
            return ""
        try:
            container = self._client.containers.get(container_id)
            logs = container.logs(tail=tail, timestamps=True)
            return logs.decode("utf-8", errors="replace") if isinstance(logs, bytes) else str(logs)
        except (NotFound, APIError) as e:
            logger.error(f"Failed to get logs for {container_id}: {e}")
            return ""

    async def container_stats(self, container_id: str) -> Optional[dict]:
        if not self._client:
            return None
        try:
            container = self._client.containers.get(container_id)
            stats = container.stats(stream=False)
            cpu_delta = stats.get("cpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0) - stats.get("precpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0)
            system_delta = stats.get("cpu_stats", {}).get("system_cpu_usage", 0) - stats.get("precpu_stats", {}).get("system_cpu_usage", 0)
            num_cpus = stats.get("cpu_stats", {}).get("online_cpus", 1)
            cpu_percent = (cpu_delta / system_delta) * num_cpus * 100 if system_delta > 0 else 0
            mem = stats.get("memory_stats", {})
            mem_usage = mem.get("usage", 0)
            mem_limit = mem.get("limit", 1)
            mem_percent = (mem_usage / mem_limit) * 100 if mem_limit > 0 else 0
            return {
                "container_id": container_id,
                "cpu_percent": round(cpu_percent, 1),
                "memory_bytes": mem_usage,
                "memory_limit": mem_limit,
                "memory_percent": round(mem_percent, 1),
                "pids": stats.get("pids_stats", {}).get("current", 0),
                "network_rx": stats.get("networks", {}).get("eth0", {}).get("rx_bytes", 0),
                "network_tx": stats.get("networks", {}).get("eth0", {}).get("tx_bytes", 0),
            }
        except (NotFound, APIError) as e:
            logger.error(f"Failed to get stats for {container_id}: {e}")
            return None

    async def exec_command(self, container_id: str, command: str, workdir: str = None) -> Optional[dict]:
        if not self._client:
            return None
        try:
            container = self._client.containers.get(container_id)
            exec_id = container.exec_run(
                cmd=command,
                workdir=workdir,
                stdout=True,
                stderr=True,
            )
            return {
                "exit_code": exec_id.exit_code,
                "output": exec_id.output.decode("utf-8", errors="replace") if isinstance(exec_id.output, bytes) else str(exec_id.output),
            }
        except (NotFound, APIError) as e:
            logger.error(f"Failed to exec in container {container_id}: {e}")
            return None

    async def list_images(self) -> list[dict]:
        if not self._client:
            return []
        try:
            images = self._client.images.list()
            return [
                {
                    "id": img.short_id,
                    "tags": img.tags,
                    "created": img.attrs.get("Created", ""),
                    "size_mb": round(img.attrs.get("Size", 0) / (1024 * 1024), 1),
                }
                for img in images
            ]
        except DockerException as e:
            logger.error(f"Failed to list images: {e}")
            return []

    async def docker_info(self) -> Optional[dict]:
        if not self._client:
            return None
        try:
            info = self._client.info()
            return {
                "containers": info.get("Containers", 0),
                "running": info.get("ContainersRunning", 0),
                "paused": info.get("ContainersPaused", 0),
                "stopped": info.get("ContainersStopped", 0),
                "images": info.get("Images", 0),
                "version": info.get("ServerVersion", ""),
                "os": info.get("OperatingSystem", ""),
                "kernel": info.get("KernelVersion", ""),
                "cpus": info.get("NCPU", 0),
                "memory_gb": round(info.get("MemTotal", 0) / (1024 ** 3), 2),
            }
        except DockerException as e:
            logger.error(f"Failed to get Docker info: {e}")
            return None


manifest = PluginManifest(
    name="docker",
    version="1.0.0",
    description="Docker containers management - list, start, stop, logs, stats",
        "docker_ps", "docker_start", "docker_stop", "docker_restart",
        "docker_logs", "docker_stats", "docker_exec", "docker_info",
    ],
)
