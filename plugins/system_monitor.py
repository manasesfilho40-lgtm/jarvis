import asyncio
import logging
import os
import platform
import time
from typing import Any, Optional

from plugins.plugin_base import BasePlugin, PluginManifest, HookType

logger = logging.getLogger("plugin_system_monitor")

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class SystemMonitorPlugin(BasePlugin):
    def __init__(self, manifest: Optional[PluginManifest] = None):
        if manifest is None:
            manifest = PluginManifest(
                name="system_monitor",
                version="1.0.0",
                description="System monitoring - CPU, RAM, disk, battery, network, processes",
            )
        super().__init__(manifest)
        self._alert_threshold_cpu = 90.0
        self._alert_threshold_memory = 90.0
        self._alert_threshold_disk = 90.0

    async def on_load(self):
        self._alert_threshold_cpu = float(self.config.get("alert_threshold_cpu", 90.0))
        self._alert_threshold_memory = float(self.config.get("alert_threshold_memory", 90.0))
        self._alert_threshold_disk = float(self.config.get("alert_threshold_disk", 90.0))
        if not HAS_PSUTIL:
            logger.warning("psutil not installed. Install with: pip install psutil")
        logger.info("SystemMonitor plugin loaded")

    async def on_unload(self):
        logger.info("SystemMonitor plugin unloaded")

    async def get_cpu_info(self) -> dict:
        if not HAS_PSUTIL:
            return {"error": "psutil not installed"}
        return {
            "percent": psutil.cpu_percent(interval=0.5),
            "count": psutil.cpu_count(),
            "count_logical": psutil.cpu_count(logical=True),
            "freq_current": psutil.cpu_freq().current if psutil.cpu_freq() else 0,
            "freq_max": psutil.cpu_freq().max if psutil.cpu_freq() else 0,
            "load_avg": [round(x, 2) for x in psutil.getloadavg()] if hasattr(psutil, "getloadavg") else [],
        }

    async def get_memory_info(self) -> dict:
        if not HAS_PSUTIL:
            return {"error": "psutil not installed"}
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return {
            "total_gb": round(mem.total / (1024 ** 3), 2),
            "available_gb": round(mem.available / (1024 ** 3), 2),
            "used_gb": round(mem.used / (1024 ** 3), 2),
            "percent": mem.percent,
            "swap_total_gb": round(swap.total / (1024 ** 3), 2),
            "swap_used_gb": round(swap.used / (1024 ** 3), 2),
            "swap_percent": swap.percent,
        }

    async def get_disk_info(self) -> list[dict]:
        if not HAS_PSUTIL:
            return [{"error": "psutil not installed"}]
        partitions = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                partitions.append({
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "total_gb": round(usage.total / (1024 ** 3), 2),
                    "used_gb": round(usage.used / (1024 ** 3), 2),
                    "free_gb": round(usage.free / (1024 ** 3), 2),
                    "percent": usage.percent,
                })
            except (PermissionError, FileNotFoundError):
                continue
        return partitions

    async def get_battery_info(self) -> Optional[dict]:
        if not HAS_PSUTIL:
            return None
        battery = psutil.sensors_battery()
        if battery:
            return {
                "percent": battery.percent,
                "power_plugged": battery.power_plugged,
                "secsleft": battery.secsleft,
            }
        return None

    async def get_network_info(self) -> dict:
        if not HAS_PSUTIL:
            return {"error": "psutil not installed"}
        net = psutil.net_io_counters()
        return {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
            "packets_sent": net.packets_sent,
            "packets_recv": net.packets_recv,
            "bytes_sent_mb": round(net.bytes_sent / (1024 ** 2), 2),
            "bytes_recv_mb": round(net.bytes_recv / (1024 ** 2), 2),
        }

    async def get_system_info(self) -> dict:
        boot_time = psutil.boot_time() if HAS_PSUTIL else 0
        uptime_days = round((time.time() - boot_time) / 86400, 2) if HAS_PSUTIL else 0
        return {
            "hostname": platform.node(),
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "boot_time": boot_time,
            "uptime_days": uptime_days,
            "python_version": platform.python_version(),
        }

    async def get_top_processes(self, limit: int = 10) -> list[dict]:
        if not HAS_PSUTIL:
            return []
        processes = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status", "create_time"]):
            try:
                pinfo = proc.info
                processes.append({
                    "pid": pinfo["pid"],
                    "name": pinfo["name"],
                    "cpu": pinfo["cpu_percent"] or 0,
                    "memory": round(pinfo["memory_percent"] or 0, 1),
                    "status": pinfo["status"],
                    "created": pinfo["create_time"],
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        processes.sort(key=lambda x: x["cpu"], reverse=True)
        return processes[:limit]

    async def kill_process(self, pid: int) -> bool:
        if not HAS_PSUTIL:
            return False
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            logger.info(f"Process {pid} terminated")
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logger.error(f"Failed to kill process {pid}: {e}")
            return False

    async def get_full_status(self) -> dict:
        cpu = await self.get_cpu_info()
        memory = await self.get_memory_info()
        disk = await self.get_disk_info()
        battery = await self.get_battery_info()
        net = await self.get_network_info()
        sysinfo = await self.get_system_info()
        processes = await self.get_top_processes(5)
        return {
            "system": sysinfo,
            "cpu": cpu,
            "memory": memory,
            "disk": disk,
            "battery": battery,
            "network": net,
            "top_processes": processes,
            "alerts": await self._check_alerts(cpu, memory, disk),
        }

    async def _check_alerts(self, cpu: dict, memory: dict, disk: list[dict]) -> list[str]:
        alerts = []
        if isinstance(cpu, dict) and cpu.get("percent", 0) > self._alert_threshold_cpu:
            alerts.append(f"CPU at {cpu['percent']}% (threshold: {self._alert_threshold_cpu}%)")
        if isinstance(memory, dict) and memory.get("percent", 0) > self._alert_threshold_memory:
            alerts.append(f"Memory at {memory['percent']}% (threshold: {self._alert_threshold_memory}%)")
        if isinstance(disk, list):
            for d in disk:
                if d.get("percent", 0) > self._alert_threshold_disk:
                    alerts.append(f"Disk {d['mountpoint']} at {d['percent']}% (threshold: {self._alert_threshold_disk}%)")
        return alerts


manifest = PluginManifest(
    name="system_monitor",
    version="1.0.0",
    description="System monitoring - CPU, RAM, disk, battery, network, processes",
)
