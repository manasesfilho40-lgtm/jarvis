import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from providers.provider_manager import ToolCall, ToolDefinition, get_manager

logger = logging.getLogger("reasoning_engine")


class ReasoningStep(Enum):
    UNDERSTAND = "understand"
    DECOMPOSE = "decompose"
    ANALYZE = "analyze"
    SYNTHESIZE = "synthesize"
    VERIFY = "verify"


@dataclass
class ReasoningTrace:
    goal: str
    steps: list[dict] = field(default_factory=list)
    conclusion: str = ""
    confidence: float = 0.0
    duration_ms: float = 0.0
    model_used: str = ""


class ReasoningEngine:
    def __init__(self):
        self._provider_mgr = get_manager()
        self._trace_history: list[ReasoningTrace] = []
        self._max_history = 50
        self._cot_template = """You are a reasoning engine. Analyze the following step by step.

Goal: {goal}

Context: {context}

Think through this carefully:
1. What exactly is being asked?
2. What information do I need?
3. What are the possible approaches?
4. What is the best approach?
5. What could go wrong?
6. Final answer:

Respond in JSON format:
{{
    "understanding": "what the goal means",
    "approach": "the chosen approach",
    "steps": ["step 1", "step 2"],
    "risks": ["risk 1"],
    "conclusion": "final concise answer",
    "confidence": 0.95
}}"""

    async def reason(self, goal: str, context: str = "", provider: str = "") -> ReasoningTrace:
        start = time.time()
        trace = ReasoningTrace(goal=goal)

        prompt = self._cot_template.format(goal=goal, context=context)
        try:
            response = await self._provider_mgr.reason_async(prompt, provider=provider)
            trace.model_used = response.model
            trace.duration_ms = response.latency_ms

            text = response.text.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            result = json.loads(text)

            trace.steps = [
                {"phase": ReasoningStep.UNDERSTAND.value, "output": result.get("understanding", "")},
                {"phase": ReasoningStep.DECOMPOSE.value, "output": str(result.get("steps", []))},
                {"phase": ReasoningStep.ANALYZE.value, "output": result.get("approach", "")},
                {"phase": ReasoningStep.SYNTHESIZE.value, "output": result.get("conclusion", "")},
                {"phase": ReasoningStep.VERIFY.value, "output": str(result.get("risks", []))},
            ]
            trace.conclusion = result.get("conclusion", text[:500])
            trace.confidence = result.get("confidence", 0.5)

        except Exception as e:
            logger.error(f"Reasoning failed: {e}")
            trace.conclusion = f"Reasoning error: {e}"
            trace.confidence = 0.0

        self._trace_history.append(trace)
        if len(self._trace_history) > self._max_history:
            self._trace_history = self._trace_history[-self._max_history:]

        return trace

    async def decompose_goal(self, goal: str, context: str = "", provider: str = "") -> list[str]:
        prompt = f"""Decompose this goal into simple, actionable sub-goals.
Goal: {goal}
Context: {context}

Return ONLY a JSON array of strings, each being a clear sub-goal.
Example: ["Search for info", "Save results to file"]
Max 5 sub-goals."""
        try:
            response = await self._provider_mgr.generate_async(prompt, provider=provider)
            text = response.text.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            goals = json.loads(text)
            return goals if isinstance(goals, list) else [goal]
        except Exception:
            return [goal]

    async def verify_solution(self, goal: str, solution: str, provider: str = "") -> dict:
        prompt = f"""Verify this solution for the given goal.

Goal: {goal}
Solution: {solution}

Check for:
- Correctness
- Completeness
- Safety
- Efficiency

Return JSON:
{{
    "valid": true/false,
    "issues": ["issue1"],
    "suggestions": ["suggestion1"],
    "confidence": 0.95
}}"""
        try:
            response = await self._provider_mgr.reason_async(prompt, provider=provider)
            text = response.text.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except Exception:
            return {"valid": True, "issues": [], "suggestions": [], "confidence": 0.5}

    def get_recent_traces(self, n: int = 5) -> list[ReasoningTrace]:
        return self._trace_history[-n:]

    def clear_history(self):
        self._trace_history.clear()


_reasoning_engine_instance = None


def get_reasoning_engine() -> ReasoningEngine:
    global _reasoning_engine_instance
    if _reasoning_engine_instance is None:
        _reasoning_engine_instance = ReasoningEngine()
    return _reasoning_engine_instance
