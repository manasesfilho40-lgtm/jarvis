import ast
import asyncio
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from core.event_bus import EventType, emit
from providers.provider_manager import get_manager

logger = logging.getLogger("self_improvement")


@dataclass
class PatchResult:
    file_path: str
    issue: str
    patch_applied: bool
    backup_path: str = ""
    error: str = ""
    improvement: str = ""


@dataclass
class ImprovementSuggestion:
    module: str
    issue_type: str
    description: str
    severity: str
    suggested_fix: str = ""
    code_snippet: str = ""


class SelfImprovement:
    def __init__(self, auto_apply: bool = False):
        self.auto_apply = auto_apply
        self._provider = get_manager()
        self._project_root = Path(__file__).resolve().parent.parent
        self._patch_history: list[PatchResult] = []
        self._improvement_log: list[ImprovementSuggestion] = []
        self._backup_dir = self._project_root / ".jarvis_backups"
        self._backup_dir.mkdir(exist_ok=True)

    async def analyze_and_improve(self, target_file: str = "") -> list[PatchResult]:
        if target_file:
            files = [Path(target_file)]
        else:
            files = self._get_python_files()

        results = []
        for filepath in files:
            if not filepath.exists():
                continue
            try:
                patch = await self._analyze_file(filepath)
                if patch:
                    results.append(patch)
            except Exception as e:
                logger.warning(f"Failed to analyze {filepath}: {e}")

        return results

    def _get_python_files(self) -> list[Path]:
        files = []
        for root, _dirs, _fnames in os.walk(self._project_root):
            for f in _fnames:
                if f.endswith(".py") and f not in ("__init__.py",):
                    path = Path(root) / f
                    rel = path.relative_to(self._project_root)
                    if "site-packages" not in str(rel) and ".git" not in str(rel):
                        files.append(path)
        return files

    async def _analyze_file(self, filepath: Path) -> Optional[PatchResult]:
        try:
            source = filepath.read_text(encoding="utf-8")
        except Exception:
            return None

        rel_path = filepath.relative_to(self._project_root)
        issues = []

        try:
            tree = ast.parse(source, filename=str(filepath))
        except SyntaxError as e:
            issues.append(f"Syntax error: {e}")
            return await self._fix_syntax(filepath, source, str(rel_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    issues.append(f"Function '{node.name}' is empty (only pass)")
                if not node.body:
                    issues.append(f"Function '{node.name}' has no body")

            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    issues.append("Bare except clause (except:) without exception type")
                elif isinstance(node.type, ast.Name) and node.type.id == "Exception":
                    pass

            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == "print":
                        issues.append("Using print() instead of logger")

            if isinstance(node, ast.Return):
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) and len(node.value.value) > 500:
                    issues.append("Very long string literal (>500 chars)")

        if issues:
            return await self._generate_patch(filepath, source, str(rel_path), issues)

        return None

    async def _fix_syntax(self, filepath: Path, source: str, rel_path: str) -> PatchResult:
        result = PatchResult(file_path=str(rel_path), issue="Syntax error", patch_applied=False)

        prompt = f"""Fix the syntax error in this Python file:

```python
{source[:3000]}
```

Analyze the error and return ONLY the fixed code. No explanation."""

        try:
            response = await self._provider.generate_async(prompt, temperature=0.1)
            fixed = response.text.strip()
            fixed = fixed.replace("```python", "").replace("```", "").strip()

            if fixed and fixed != source:
                backup = self._backup(filepath)
                filepath.write_text(fixed, encoding="utf-8")
                result.patch_applied = True
                result.backup_path = str(backup)
                result.improvement = "Syntax error fixed"
                self._patch_history.append(result)
                logger.info(f"Fixed syntax in {rel_path}")
        except Exception as e:
            result.error = str(e)

        return result

    async def _generate_patch(self, filepath: Path, source: str, rel_path: str, issues: list[str]) -> PatchResult:
        result = PatchResult(file_path=str(rel_path), issue="; ".join(issues[:3]), patch_applied=False)

        prompt = f"""Improve this Python code. Issues found:
{chr(10).join(f'- {i}' for i in issues[:5])}

CODE:
```python
{source[:4000]}
```

Improve ONLY what's needed to fix the issues. Maintain the same functionality.
Return ONLY the improved code. No explanation."""

        try:
            response = await self._provider.generate_async(prompt, temperature=0.2)
            improved = response.text.strip()
            improved = improved.replace("```python", "").replace("```", "").strip()

            if improved and improved != source:
                backup = self._backup(filepath)
                filepath.write_text(improved, encoding="utf-8")
                result.patch_applied = True
                result.backup_path = str(backup)
                result.improvement = f"Fixed: {issues[0][:100]}"
                self._patch_history.append(result)
                logger.info(f"Patched {rel_path}: {issues[0][:80]}")
        except Exception as e:
            result.error = str(e)

        return result

    async def generate_suggestion(self, module_name: str, error_context: str) -> Optional[str]:
        prompt = f"""Suggest an improvement for this module based on the error:

Module: {module_name}
Error context: {error_context}

Provide a specific, actionable fix suggestion in Brazilian Portuguese.
Focus on root cause, not symptoms."""

        try:
            response = await self._provider.reason_async(prompt)
            return response.text
        except Exception:
            return None

    async def optimize_imports(self, filepath: Path) -> bool:
        try:
            source = filepath.read_text(encoding="utf-8")
            prompt = f"""Optimize imports in this Python file. Remove unused imports, sort them properly.

```python
{source[:3000]}
```

Return ONLY the optimized code with sorted imports."""

            response = await self._provider.generate_async(prompt, temperature=0.1)
            optimized = response.text.strip()
            optimized = optimized.replace("```python", "").replace("```", "").strip()
            if optimized and optimized != source:
                self._backup(filepath)
                filepath.write_text(optimized, encoding="utf-8")
                return True
            return False
        except Exception:
            return False

    def _backup(self, filepath: Path) -> Path:
        timestamp = int(time.time())
        backup_name = f"{filepath.name}.{timestamp}.bak"
        backup_path = self._backup_dir / backup_name
        shutil.copy2(filepath, backup_path)
        return backup_path

    async def run_full_diagnostics(self) -> dict:
        files = self._get_python_files()
        results = {"checked": 0, "issues_found": 0, "fixed": 0, "errors": []}
        for filepath in files:
            results["checked"] += 1
            patch = await self._analyze_file(filepath)
            if patch:
                results["issues_found"] += 1
                if patch.patch_applied:
                    results["fixed"] += 1
        return results

    def get_patch_history(self) -> list[PatchResult]:
        return list(self._patch_history)

    def rollback_last_patch(self) -> bool:
        if not self._patch_history:
            return False
        last = self._patch_history.pop()
        if last.backup_path and os.path.exists(last.backup_path):
            filepath = self._project_root / last.file_path
            shutil.copy2(last.backup_path, filepath)
            return True
        return False


_self_improvement_instance = None


def get_self_improvement(auto_apply: bool = False) -> SelfImprovement:
    global _self_improvement_instance
    if _self_improvement_instance is None:
        _self_improvement_instance = SelfImprovement(auto_apply=auto_apply)
    return _self_improvement_instance
