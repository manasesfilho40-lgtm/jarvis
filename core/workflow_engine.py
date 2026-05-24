import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger("workflow_engine")


class WorkflowStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStepType(Enum):
    VISION_CAPTURE = "vision_capture"
    VISION_ANALYZE = "vision_analyze"
    BROWSER_NAVIGATE = "browser_navigate"
    BROWSER_CLICK = "browser_click"
    BROWSER_SEARCH = "browser_search"
    BROWSER_EXTRACT = "browser_extract"
    VOICE_SPEAK = "voice_speak"
    VOICE_LISTEN = "voice_listen"
    SYSTEM_COMMAND = "system_command"
    SHELL_EXEC = "shell_exec"
    THINK = "think"
    CODE_GENERATE = "code_generate"
    CODE_EXECUTE = "code_execute"
    WAIT = "wait"
    CONDITIONAL = "conditional"
    LOOP = "loop"
    SUBWORKFLOW = "subworkflow"
    NOTIFY = "notify"
    CUSTOM = "custom"


@dataclass
class WorkflowStep:
    type: WorkflowStepType
    params: dict = field(default_factory=dict)
    name: str = ""
    step_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timeout: float = 300.0
    retry_count: int = 0
    max_retries: int = 2
    depends_on: list[str] = field(default_factory=list)
    condition: Optional[Callable] = None
    on_success: Optional["WorkflowStep"] = None
    on_failure: Optional["WorkflowStep"] = None

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "params": self.params,
            "name": self.name,
            "step_id": self.step_id,
            "timeout": self.timeout,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "depends_on": self.depends_on,
        }


@dataclass
class WorkflowStepResult:
    step: WorkflowStep
    success: bool
    data: Any = None
    error: Optional[str] = None
    duration: float = 0.0
    retries_used: int = 0


@dataclass
class Workflow:
    name: str
    steps: list[WorkflowStep] = field(default_factory=list)
    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: WorkflowStatus = WorkflowStatus.PENDING
    context: dict = field(default_factory=dict)
    results: dict[str, WorkflowStepResult] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    max_concurrency: int = 1
    on_complete: Optional[Callable] = None
    on_step_complete: Optional[Callable] = None
    on_error: Optional[Callable] = None

    @property
    def duration(self) -> float:
        if self.completed_at and self.started_at:
            return self.completed_at - self.started_at
        if self.started_at:
            return time.time() - self.started_at
        return 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "steps": len(self.steps),
            "completed_steps": sum(1 for r in self.results.values() if r.success),
            "failed_steps": sum(1 for r in self.results.values() if not r.success),
            "duration": self.duration,
            "created_at": self.created_at,
        }


class WorkflowEngine:
    def __init__(self):
        self._workflows: dict[str, Workflow] = {}
        self._action_handlers: dict[WorkflowStepType, list[Callable]] = {}
        self._running = False
        self._register_default_handlers()

    def _register_default_handlers(self):
        self.register_handler(WorkflowStepType.SYSTEM_COMMAND, self._handle_system_command)
        self.register_handler(WorkflowStepType.SHELL_EXEC, self._handle_shell_exec)
        self.register_handler(WorkflowStepType.VOICE_SPEAK, self._handle_voice_speak)
        self.register_handler(WorkflowStepType.VISION_CAPTURE, self._handle_vision_capture)
        self.register_handler(WorkflowStepType.VISION_ANALYZE, self._handle_vision_analyze)
        self.register_handler(WorkflowStepType.BROWSER_NAVIGATE, self._handle_browser_navigate)
        self.register_handler(WorkflowStepType.BROWSER_SEARCH, self._handle_browser_search)
        self.register_handler(WorkflowStepType.BROWSER_EXTRACT, self._handle_browser_extract)
        self.register_handler(WorkflowStepType.CODE_GENERATE, self._handle_code_generate)
        self.register_handler(WorkflowStepType.CUSTOM, self._handle_custom)

    def register_handler(self, step_type: WorkflowStepType, handler: Callable):
        if step_type not in self._action_handlers:
            self._action_handlers[step_type] = []
        self._action_handlers[step_type].append(handler)
        logger.debug(f"Handler registered for {step_type.value}")

    def create_workflow(self, name: str, steps: list[WorkflowStep], **kwargs) -> Workflow:
        workflow = Workflow(name=name, steps=steps, **kwargs)
        self._workflows[workflow.workflow_id] = workflow
        logger.info(f"Workflow '{name}' created ({workflow.workflow_id[:8]}...)")
        return workflow

    async def execute_workflow(self, workflow: Workflow):
        workflow.status = WorkflowStatus.RUNNING
        workflow.started_at = time.time()

        try:
            await self._execute_steps(workflow)
        except asyncio.CancelledError:
            workflow.status = WorkflowStatus.CANCELLED
            logger.warning(f"Workflow '{workflow.name}' cancelled")
        except Exception as e:
            workflow.status = WorkflowStatus.FAILED
            logger.error(f"Workflow '{workflow.name}' failed: {e}")
            if workflow.on_error:
                try:
                    await workflow.on_error(workflow, e)
                except Exception:
                    pass
        finally:
            workflow.completed_at = time.time()
            if workflow.status == WorkflowStatus.RUNNING:
                workflow.status = WorkflowStatus.COMPLETED

            if workflow.status == WorkflowStatus.COMPLETED and workflow.on_complete:
                try:
                    await workflow.on_complete(workflow)
                except Exception as e:
                    logger.error(f"Workflow on_complete failed: {e}")

            logger.info(f"Workflow '{workflow.name}' {workflow.status.value} in {workflow.duration:.2f}s")

    async def _execute_steps(self, workflow: Workflow, steps: list[WorkflowStep] = None):
        if steps is None:
            steps = workflow.steps

        semaphore = asyncio.Semaphore(workflow.max_concurrency)

        async def _run_step(step: WorkflowStep):
            async with semaphore:
                for dep_id in step.depends_on:
                    dep_result = workflow.results.get(dep_id)
                    if dep_result and not dep_result.success:
                        workflow.results[step.step_id] = WorkflowStepResult(
                            step=step, success=False,
                            error=f"Dependency {dep_id} failed",
                        )
                        return

                result = await self._execute_step(workflow, step)
                workflow.results[step.step_id] = result

                if result.success and step.on_success:
                    await self._execute_step(workflow, step.on_success)
                elif not result.success and step.on_failure:
                    await self._execute_step(workflow, step.on_failure)

                if workflow.on_step_complete:
                    try:
                        await workflow.on_step_complete(workflow, step, result)
                    except Exception:
                        pass

        tasks = [_run_step(s) for s in steps]
        await asyncio.gather(*tasks)

    async def _execute_step(self, workflow: Workflow, step: WorkflowStep) -> WorkflowStepResult:
        start = time.time()
        retries = 0

        while retries <= step.max_retries:
            try:
                result = await asyncio.wait_for(
                    self._dispatch_step(workflow, step),
                    timeout=step.timeout,
                )
                return WorkflowStepResult(
                    step=step, success=True, data=result,
                    duration=time.time() - start, retries_used=retries,
                )
            except asyncio.TimeoutError:
                retries += 1
                logger.warning(f"Step '{step.name}' timed out (retry {retries}/{step.max_retries})")
                if retries > step.max_retries:
                    return WorkflowStepResult(
                        step=step, success=False,
                        error=f"Timeout after {step.timeout}s",
                        duration=time.time() - start, retries_used=retries,
                    )
            except Exception as e:
                retries += 1
                logger.warning(f"Step '{step.name}' failed: {e} (retry {retries}/{step.max_retries})")
                if retries > step.max_retries:
                    return WorkflowStepResult(
                        step=step, success=False,
                        error=str(e),
                        duration=time.time() - start, retries_used=retries,
                    )

        return WorkflowStepResult(
            step=step, success=False,
            error="Max retries exceeded",
            duration=time.time() - start, retries_used=retries,
        )

    async def _dispatch_step(self, workflow: Workflow, step: WorkflowStep) -> Any:
        if step.condition and not step.condition(workflow.context):
            return {"skipped": True, "reason": "condition not met"}

        step_type = step.type

        if step_type == WorkflowStepType.WAIT:
            duration = step.params.get("duration", 1.0)
            await asyncio.sleep(duration)
            return {"waited": duration}

        if step_type == WorkflowStepType.THINK:
            thought = step.params.get("thought", "")
            await asyncio.sleep(0.1)
            return {"thought": thought}

        if step_type == WorkflowStepType.SUBWORKFLOW:
            sub_id = step.params.get("workflow_id")
            sub = self._workflows.get(sub_id)
            if sub:
                sub.context.update(workflow.context)
                await self.execute_workflow(sub)
                return sub.results
            raise ValueError(f"Sub-workflow {sub_id} not found")

        if step_type == WorkflowStepType.NOTIFY:
            message = step.params.get("message", "")
            level = step.params.get("level", "info")
            try:
                from core.event_bus import EventBus, get_bus
                bus = get_bus()
                await bus.emit(f"notification.{level}", source="workflow", data={
                    "message": message, "workflow": workflow.workflow_id,
                })
            except Exception:
                pass
            return {"notified": message}

        handlers = self._action_handlers.get(step.type, [])
        if not handlers:
            raise ValueError(f"No handler for step type: {step.type.value}")

        for handler in handlers:
            result = handler(workflow, step, workflow.context)
            if hasattr(result, "__await__"):
                result = await result
            if result is not None:
                if isinstance(result, dict):
                    workflow.context.update(result)
                return result

        return {"handled": True}

    async def _handle_system_command(self, workflow: Workflow, step: WorkflowStep, context: dict) -> dict:
        import subprocess
        command = step.params.get("command", "")
        cwd = step.params.get("cwd", context.get("cwd", "."))
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=step.timeout, cwd=cwd,
            )
            output = result.stdout[-1000:] if result.stdout else ""
            context["last_command_output"] = output
            return {"command": command, "output": output, "returncode": result.returncode}
        except subprocess.TimeoutExpired:
            return {"command": command, "error": "timeout"}
        except Exception as e:
            return {"command": command, "error": str(e)}

    async def _handle_shell_exec(self, workflow: Workflow, step: WorkflowStep, context: dict) -> dict:
        import subprocess
        command = step.params.get("command", "")
        cwd = step.params.get("cwd", context.get("cwd", "."))
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=step.timeout, cwd=cwd,
            )
            context["shell_output"] = result.stdout[-2000:]
            return {"stdout": result.stdout[-2000:], "stderr": result.stderr[-500:], "returncode": result.returncode}
        except Exception as e:
            return {"error": str(e)}

    async def _handle_voice_speak(self, workflow: Workflow, step: WorkflowStep, context: dict) -> dict:
        text = step.params.get("text", "")
        text = self._interpolate(text, context)
        async_mode = step.params.get("async", False)
        try:
            from voice.voice_pipeline import get_pipeline
            pipeline = get_pipeline()
            if async_mode:
                await pipeline.speak_async(text)
            else:
                await pipeline.speak(text)
            return {"spoken": text[:100]}
        except Exception as e:
            logger.warning(f"Voice speak failed: {e}")
            return {"spoken": text[:100], "error": str(e)}

    async def _handle_vision_capture(self, workflow: Workflow, step: WorkflowStep, context: dict) -> dict:
        monitor = step.params.get("monitor", 1)
        try:
            from vision.screen_analyzer import get_analyzer
            analyzer = get_analyzer()
            analysis = analyzer.capture_screen()
            context["last_capture"] = analysis
            return {"captured": True, "monitor": monitor}
        except Exception as e:
            return {"captured": False, "error": str(e)}

    async def _handle_vision_analyze(self, workflow: Workflow, step: WorkflowStep, context: dict) -> dict:
        try:
            from vision.screen_analyzer import get_analyzer
            analyzer = get_analyzer()
            analysis = analyzer.analyze_screen(detect_text=step.params.get("detect_text", True))
            summary = f"Screen analysis: {analysis.text_length if hasattr(analysis, 'text_length') else 0} chars"
            context["analysis_summary"] = summary
            context["screen_analysis"] = analysis
            return {"summary": summary}
        except Exception as e:
            return {"error": str(e)}

    async def _handle_browser_navigate(self, workflow: Workflow, step: WorkflowStep, context: dict) -> dict:
        url = step.params.get("url", "about:blank")
        try:
            from browser.browser_agent import get_browser_agent
            agent = get_browser_agent()
            result = await agent.navigate(url)
            context["last_url"] = url
            return {"url": url, "result": str(result)[:200]}
        except Exception as e:
            return {"url": url, "error": str(e)}

    async def _handle_browser_search(self, workflow: Workflow, step: WorkflowStep, context: dict) -> dict:
        query = step.params.get("query", "")
        query = self._interpolate(query, context)
        engine = step.params.get("engine", "google")
        try:
            from browser.browser_agent import get_browser_agent
            agent = get_browser_agent()
            result = await agent.search(query, engine=engine)
            context["search_results"] = str(result)[:500]
            context["last_query"] = query
            return {"query": query, "engine": engine, "result": str(result)[:200]}
        except Exception as e:
            return {"query": query, "error": str(e)}

    async def _handle_browser_extract(self, workflow: Workflow, step: WorkflowStep, context: dict) -> dict:
        selector = step.params.get("selector", "body")
        limit = step.params.get("limit", 5)
        try:
            from browser.browser_agent import get_browser_agent
            agent = get_browser_agent()
            page = agent.current_page
            if page:
                elements = await page.query_selector_all(selector)
                texts = [await el.inner_text() for el in elements[:limit]]
                context["extracted_texts"] = texts
                return {"extracted": len(texts), "texts": texts}
            return {"extracted": 0, "error": "no page"}
        except Exception as e:
            return {"extracted": 0, "error": str(e)}

    async def _handle_code_generate(self, workflow: Workflow, step: WorkflowStep, context: dict) -> dict:
        task = step.params.get("task", "")
        task = self._interpolate(task, context)
        context["dev_task"] = task
        return {"task": task, "status": "pending"}

    async def _handle_custom(self, workflow: Workflow, step: WorkflowStep, context: dict) -> dict:
        handler_name = step.params.get("handler", "")
        payload = step.params.get("payload", {})
        context[f"custom_{handler_name}"] = payload
        return {"handler": handler_name, "executed": True}

    def _interpolate(self, text: str, context: dict) -> str:
        import re
        def _replace(m):
            key = m.group(1)
            val = context.get(key, m.group(0))
            return str(val) if not isinstance(val, dict) else str(val)
        return re.sub(r"\{\{(\w+)\}\}", _replace, text)

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        return self._workflows.get(workflow_id)

    def get_running_workflows(self) -> list[Workflow]:
        return [w for w in self._workflows.values() if w.status == WorkflowStatus.RUNNING]

    def get_recent_workflows(self, limit: int = 20) -> list[Workflow]:
        return sorted(
            self._workflows.values(),
            key=lambda w: w.created_at, reverse=True,
        )[:limit]


_workflow_engine_instance = None


def get_workflow_engine() -> WorkflowEngine:
    global _workflow_engine_instance
    if _workflow_engine_instance is None:
        _workflow_engine_instance = WorkflowEngine()
    return _workflow_engine_instance
