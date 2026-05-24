import asyncio
import logging
import os
import platform
import time
from typing import Any, Optional

import psutil
from agents.agent_base import BaseAgent
from core.event_bus import EventType, emit
from core.runtime import get_runtime

logger = logging.getLogger("system_agent")


class SystemAgent(BaseAgent):
    def __init__(self, monitor_interval: float = 10.0):
        super().__init__("system", "System monitoring, diagnostics, and optimization")
        self.monitor_interval = monitor_interval
        self._last_monitor = 0.0
        self._thresholds = {
            "cpu_warning": 80.0,
            "memory_warning": 85.0,
            "disk_warning": 90.0,
            "temperature_warning": 85.0,
        }

    async def think(self, context: dict) -> Optional[dict]:
        now = time.time()
        if now - self._last_monitor < self.monitor_interval:
            return None
        self._last_monitor = now

        diagnostics = await self._run_diagnostics()
        issues = self._check_issues(diagnostics)

        if issues:
            emit(EventType.SYSTEM_WARNING, {"issues": issues, "diagnostics": diagnostics}, source=self.name)

        return {"action": "monitor", "diagnostics": diagnostics, "issues": issues}

    async def act(self, thought: dict) -> Any:
        if thought and thought.get("issues"):
            for issue in thought["issues"][:3]:
                self.log(f"Issue detected: {issue}", level="warning")
        return thought

    async def _run_diagnostics(self) -> dict:
        try:
            cpu = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            net = psutil.net_io_counters()
            boot = psutil.boot_time()
            uptime_seconds = time.time() - boot

            result = {
                "cpu": {"percent": cpu, "cores": psutil.cpu_count(), "physical_cores": psutil.cpu_count(logical=False)},
                "memory": {"percent": memory.percent, "used_gb": memory.used / 1e9, "total_gb": memory.total / 1e9},
                "disk": {"percent": disk.percent, "free_gb": disk.free / 1e9, "total_gb": disk.total / 1e9},
                "network": {"bytes_sent_mb": net.bytes_sent / 1e6, "bytes_recv_mb": net.bytes_recv / 1e6},
                "uptime_hours": round(uptime_seconds / 3600, 1),
                "processes": len(psutil.pids()),
                "platform": platform.platform(),
                "python_version": platform.python_version(),
            }

            try:
                import GPUtil
                gpus = GPUtil.getGPUs()
                if gpus:
                    result["gpu"] = {"name": gpus[0].name, "load": gpus[0].load * 100, "memory": gpus[0].memoryUtil * 100}
            except Exception:
                pass

            self._runtime.update_system(cpu_usage=cpu, memory_usage=memory.percent)
            return result
        except Exception as e:
            return {"error": str(e)}

    def _check_issues(self, diagnostics: dict) -> list[str]:
        issues = []
        if diagnostics.get("cpu", {}).get("percent", 0) > self._thresholds["cpu_warning"]:
            issues.append(f"CPU at {diagnostics['cpu']['percent']}% (threshold: {self._thresholds['cpu_warning']}%)")
        if diagnostics.get("memory", {}).get("percent", 0) > self._thresholds["memory_warning"]:
            issues.append(f"Memory at {diagnostics['memory']['percent']}% (threshold: {self._thresholds['memory_warning']}%)")
        if diagnostics.get("disk", {}).get("percent", 0) > self._thresholds["disk_warning"]:
            issues.append(f"Disk at {diagnostics['disk']['percent']}% (threshold: {self._thresholds['disk_warning']}%)")
        return issues

    async def get_system_info(self) -> dict:
        return await self._run_diagnostics()

    async def kill_process(self, process_name: str) -> bool:
        try:
            for proc in psutil.process_iter(["name"]):
                try:
                    if proc.info["name"] and process_name.lower() in proc.info["name"].lower():
                        proc.kill()
                        return True
                except Exception:
                    continue
            return False
        except Exception:
            return False

    async def get_disk_usage(self, path: str = "/") -> dict:
        try:
            usage = psutil.disk_usage(path)
            return {
                "total_gb": round(usage.total / 1e9, 2),
                "used_gb": round(usage.used / 1e9, 2),
                "free_gb": round(usage.free / 1e9, 2),
                "percent": usage.percent,
            }
        except Exception as e:
            return {"error": str(e)}

    async def get_battery_status(self) -> dict:
        try:
            battery = psutil.sensors_battery()
            if battery:
                return {
                    "percent": battery.percent,
                    "charging": battery.power_plugged,
                    "remaining_seconds": battery.secsleft if battery.secsleft > 0 else 0,
                }
            return {"error": "No battery detected"}
        except Exception:
            return {"error": "Could not read battery"}

    def subscribe_to_events(self):
        self.subscribe_to(EventType.SYSTEM_ERROR, EventType.SYSTEM_WARNING)


_system_agent_instance = None


def get_system_agent() -> SystemAgent:
    global _system_agent_instance
    if _system_agent_instance is None:
        _system_agent_instance = SystemAgent()
    return _system_agent_instance
