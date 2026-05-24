import ast
import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from agents.agent_base import BaseAgent
from core.event_bus import EventType, emit
from providers.provider_manager import get_manager

logger = logging.getLogger("coding_agent")


class CodingAgent(BaseAgent):
    def __init__(self):
        super().__init__("coding", "Code generation, analysis, and debugging")
        self._provider = get_manager()
        self._sandbox_dir = Path(tempfile.gettempdir()) / "jarvis_code_sandbox"
        self._sandbox_dir.mkdir(exist_ok=True)

    async def think(self, context: dict) -> Optional[dict]:
        return {"action": "idle", "agent": "coding"}

    async def act(self, thought: dict) -> Any:
        return thought

    async def generate_code(self, description: str, language: str = "python", output_path: str = "") -> str:
        emit(EventType.AGENT_THOUGHT, {"agent": "coding", "thought": f"Generating {language} code: {description[:60]}..."}, source="coding")

        prompt = f"""You are an expert {language} developer. Generate production-quality code.

TASK: {description}

REQUIREMENTS:
- Complete, working code
- Proper error handling
- Type hints where applicable
- No placeholders or TODOs
- Safe execution (no destructive operations)

Return ONLY the code. No explanation, no markdown."""

        response = await self._provider.generate_async(prompt, temperature=0.2)
        code = response.text.strip()
        code = self._clean_code(code, language)

        if output_path:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(code, encoding="utf-8")

        return code

    async def review_code(self, code: str, language: str = "python") -> dict:
        prompt = f"""Review this {language} code for bugs, security issues, and improvements:

```{language}
{code[:4000]}
```

Analyze:
1. Logic errors
2. Security vulnerabilities
3. Performance issues
4. Code style improvements
5. Missing error handling

Return JSON:
{{
    "has_bugs": true/false,
    "bugs": [{{"line": 1, "description": "...", "severity": "high"}}],
    "security_issues": [...],
    "suggestions": [...],
    "rating": "good/fair/poor"
}}"""

        response = await self._provider.reason_async(prompt)
        text = response.text.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(text)
        except Exception:
            return {"has_bugs": False, "bugs": [], "suggestions": [], "rating": "unknown"}

    async def fix_code(self, code: str, error: str, language: str = "python") -> str:
        prompt = f"""Fix this {language} code that has an error:

CODE:
```{language}
{code[:3000]}
```

ERROR:
{error}

Return ONLY the fixed code. No explanation."""

        response = await self._provider.generate_async(prompt, temperature=0.2)
        return self._clean_code(response.text, language)

    async def run_code_safe(self, code: str, timeout: int = 30) -> dict:
        filepath = self._sandbox_dir / f"script_{int(time.time())}.py"
        try:
            filepath.write_text(code, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(filepath)],
                capture_output=True, text=True,
                timeout=timeout, cwd=str(self._sandbox_dir),
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout[-2000:],
                "stderr": result.stderr[-2000:],
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            try:
                filepath.unlink()
            except Exception:
                pass

    async def explain_code(self, code: str, language: str = "python") -> str:
        prompt = f"""Explain this {language} code in Brazilian Portuguese:

```{language}
{code[:3000]}
```

Explain what it does, key concepts, and how it works."""

        response = await self._provider.generate_async(prompt, temperature=0.3)
        return response.text

    def _clean_code(self, code: str, language: str) -> str:
        code = re.sub(r"^```(?:\w+)?", "", code.strip(), flags=re.MULTILINE)
        code = code.rstrip("`").strip()
        return code

    async def refactor_code(self, code: str, instructions: str, language: str = "python") -> str:
        prompt = f"""Refactor this {language} code according to the instructions:

INSTRUCTIONS: {instructions}

CODE:
```{language}
{code[:4000]}
```

Return ONLY the refactored code."""

        response = await self._provider.generate_async(prompt, temperature=0.2)
        return self._clean_code(response.text, language)

    def subscribe_to_events(self):
        self.subscribe_to(EventType.TASK_CREATED, EventType.TASK_FAILED)


_coding_agent_instance = None


def get_coding_agent() -> CodingAgent:
    global _coding_agent_instance
    if _coding_agent_instance is None:
        _coding_agent_instance = CodingAgent()
    return _coding_agent_instance
