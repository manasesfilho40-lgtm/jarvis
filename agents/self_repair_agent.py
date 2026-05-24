import ast
import logging
import os
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Optional

from core.event_bus import EventBus, EventType, get_bus
from agents.agent_base import AgentStatus, BaseAgent

logger = logging.getLogger("self_repair_agent")


@dataclass
class DiagnosticResult:
    module: str
    issue_type: str
    severity: str
    line: Optional[int] = None
    message: str = ""
    suggestion: str = ""
    fix_type: Optional[str] = None


@dataclass
class Repair:
    diagnostic: DiagnosticResult
    fixed: bool = False
    backup_path: Optional[str] = None
    error: Optional[str] = None


class SelfRepairAgent(BaseAgent):
    def __init__(self, repair_interval: float = 120.0, auto_repair: bool = False):
        super().__init__(name="self_repair")
        self._interval = repair_interval
        self._auto_repair = auto_repair
        self._last_repair_time = 0.0
        self._diagnostics: list[DiagnosticResult] = []
        self._repair_history: list[Repair] = []
        self._import_cache: dict[str, bool] = {}
        self._project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._core_modules = [
            "core", "providers", "memory", "agents",
            "vision", "browser", "voice", "security", "plugins",
        ]

    async def on_start(self):
        logger.info(f"Self-Repair Agent started (interval={self._interval}s, auto_repair={self._auto_repair})")
        self.subscribe_to(EventType.ERROR_DETECTED, EventType.TASK_FAILED)

    async def on_stop(self):
        logger.info("Self-Repair Agent stopped")

    async def think(self) -> Optional[str]:
        if time.time() - self._last_repair_time < self._interval:
            return None

        self._diagnostics.clear()
        self._diagnostics.extend(await self._run_import_checks())
        self._diagnostics.extend(await self._run_syntax_checks())
        self._diagnostics.extend(await self._run_consistency_checks())

        critical = [d for d in self._diagnostics if d.severity == "critical"]
        errors = [d for d in self._diagnostics if d.severity == "error"]
        warnings = [d for d in self._diagnostics if d.severity == "warning"]

        if not self._diagnostics:
            bus = get_bus()
            await bus.emit(EventType.INFO_LOG, source="self_repair", data={"message": "No issues found"})
            self._last_repair_time = time.time()
            return "No issues detected in codebase"

        await self._report_diagnostics()

        if self._auto_repair and critical:
            await self._attempt_auto_repair()

        self._last_repair_time = time.time()
        return f"Found {len(critical)} critical, {len(errors)} error, {len(warnings)} warning issues"

    async def act(self, thought: str) -> Any:
        if not thought:
            return None
        if self._auto_repair and "critical" in thought:
            await self._attempt_auto_repair()
        return self._diagnostics

    async def observe(self) -> dict:
        return {
            "last_repair_time": self._last_repair_time,
            "diagnostics_count": len(self._diagnostics),
            "repairs_attempted": len(self._repair_history),
            "repairs_succeeded": sum(1 for r in self._repair_history if r.fixed),
            "auto_repair": self._auto_repair,
            "healthy": len([d for d in self._diagnostics if d.severity == "critical"]) == 0,
        }

    async def _run_import_checks(self) -> list[DiagnosticResult]:
        results = []
        for mod_name in self._core_modules:
            mod_path = os.path.join(self._project_root, mod_name)
            if not os.path.isdir(mod_path):
                results.append(DiagnosticResult(
                    module=mod_name,
                    issue_type="missing_module",
                    severity="critical",
                    message=f"Module directory '{mod_name}' not found",
                ))
                continue

            for root, _dirs, files in os.walk(mod_path):
                for f in files:
                    if not f.endswith(".py"):
                        continue
                    filepath = os.path.join(root, f)
                    relpath = os.path.relpath(filepath, self._project_root)

                    try:
                        with open(filepath, "r", encoding="utf-8") as fh:
                            source = fh.read()
                        tree = ast.parse(source, filename=filepath)
                    except SyntaxError as e:
                        results.append(DiagnosticResult(
                            module=mod_name,
                            issue_type="syntax_error",
                            severity="critical",
                            line=getattr(e, "lineno", None),
                            message=f"Syntax error in {relpath}: {e}",
                            fix_type="syntax",
                        ))
                        continue
                    except Exception as e:
                        results.append(DiagnosticResult(
                            module=mod_name,
                            issue_type="read_error",
                            severity="error",
                            message=f"Cannot read {relpath}: {e}",
                        ))
                        continue

                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                if alias.name in self._import_cache:
                                    continue
                                try:
                                    importlib = __import__(alias.name.split(".")[0])
                                    self._import_cache[alias.name] = True
                                except ImportError:
                                    self._import_cache[alias.name] = False
                                    results.append(DiagnosticResult(
                                        module=mod_name,
                                        issue_type="missing_import",
                                        severity="warning",
                                        line=getattr(node, "lineno", None),
                                        message=f"Missing import '{alias.name}' in {relpath}",
                                        suggestion=f"pip install {alias.name}",
                                    ))
                        elif isinstance(node, ast.ImportFrom):
                            if node.module:
                                if node.module in self._import_cache:
                                    continue
                                try:
                                    importlib = __import__(node.module.split(".")[0])
                                    self._import_cache[node.module] = True
                                except ImportError:
                                    self._import_cache[node.module] = False
                                    results.append(DiagnosticResult(
                                        module=mod_name,
                                        issue_type="missing_import",
                                        severity="warning",
                                        line=getattr(node, "lineno", None),
                                        message=f"Missing import '{node.module}' in {relpath}",
                                        suggestion=f"pip install {node.module}",
                                    ))
        return results

    async def _run_syntax_checks(self) -> list[DiagnosticResult]:
        return []

    async def _run_consistency_checks(self) -> list[DiagnosticResult]:
        results = []

        expected_init_files = [
            "core/__init__.py",
            "providers/__init__.py",
            "memory/__init__.py",
            "agents/__init__.py",
            "vision/__init__.py",
            "browser/__init__.py",
            "voice/__init__.py",
            "security/__init__.py",
            "plugins/__init__.py",
        ]
        for init_rel in expected_init_files:
            init_path = os.path.join(self._project_root, init_rel)
            if not os.path.exists(init_path):
                results.append(DiagnosticResult(
                    module=os.path.dirname(init_rel),
                    issue_type="missing_init",
                    severity="warning",
                    message=f"Missing {init_rel}",
                    fix_type="create_init",
                    suggestion=f"Create {init_rel}",
                ))
                try:
                    os.makedirs(os.path.dirname(init_path), exist_ok=True)
                    with open(init_path, "w") as f:
                        f.write("")
                    logger.info(f"Created missing {init_rel}")
                except Exception as e:
                    logger.error(f"Failed to create {init_rel}: {e}")

        return results

    async def _report_diagnostics(self):
        bus = get_bus()
        for d in self._diagnostics:
            await bus.emit(EventType.ERROR_DETECTED, source="self_repair", data={
                "module": d.module,
                "issue_type": d.issue_type,
                "severity": d.severity,
                "line": d.line,
                "message": d.message,
                "suggestion": d.suggestion,
            })

    async def _attempt_auto_repair(self):
        for diagnostic in self._diagnostics:
            if diagnostic.fix_type == "create_init":
                continue

            repair = Repair(diagnostic=diagnostic)
            try:
                filepath = os.path.join(self._project_root, diagnostic.module.replace(".", os.sep) + ".py")
                if not os.path.exists(filepath):
                    repair.error = f"File not found: {filepath}"
                    self._repair_history.append(repair)
                    continue

                backup_path = filepath + ".backup"
                with open(filepath, "r", encoding="utf-8") as f:
                    original = f.read()
                with open(backup_path, "w", encoding="utf-8") as f:
                    f.write(original)
                repair.backup_path = backup_path

                if diagnostic.fix_type == "syntax":
                    fixed = original
                    fixed = fixed.replace("\t", "    ")
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(fixed)
                    repair.fixed = True
                    logger.info(f"Auto-repair: applied syntax fix to {filepath}")

                elif diagnostic.issue_type == "missing_import":
                    pkg = diagnostic.suggestion.replace("pip install ", "")
                    if pkg:
                        result = subprocess.run(
                            [sys.executable, "-m", "pip", "install", pkg],
                            capture_output=True, text=True, timeout=120,
                        )
                        if result.returncode == 0:
                            repair.fixed = True
                            self._import_cache[diagnostic.module] = True
                            logger.info(f"Auto-repair: installed {pkg}")

            except Exception as e:
                repair.error = str(e)
                logger.error(f"Auto-repair failed for {diagnostic.module}: {e}")

            self._repair_history.append(repair)

    async def observe(self, event) -> Optional[dict]:
        data = event.data
        source = event.source
        if event.type == EventType.ERROR_DETECTED:
            self._diagnostics.append(DiagnosticResult(
                module=data.get("module", "unknown") if isinstance(data, dict) else "unknown",
                issue_type="runtime_error",
                severity="error",
                message=data.get("message", str(data)) if isinstance(data, dict) else str(data),
            ))
        elif event.type == EventType.TASK_FAILED:
            self._diagnostics.append(DiagnosticResult(
                module=data.get("module", "unknown") if isinstance(data, dict) else "unknown",
                issue_type="task_failure",
                severity="warning",
                message=data.get("error", str(data)) if isinstance(data, dict) else str(data),
            ))
        return {"type": event.type.value, "diagnostics_count": len(self._diagnostics)}
