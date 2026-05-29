"""
Workflows práticos pré-definidos para o J.A.R.V.I.S.
"""
from core.workflow_engine import WorkflowStepType, WorkflowStep, Workflow, get_workflow_engine

engine = get_workflow_engine()


def register_builtin_workflows():
    _register_browser_search_speak()
    _register_vision_analyze_report()
    _register_system_health_check()
    _register_voice_browser_chain()
    _register_code_dev_loop()


def _register_browser_search_speak():
    steps = [
        WorkflowStep(type=WorkflowStepType.THINK, params={"thought": "Opening browser..."}, name="think_open"),
        WorkflowStep(type=WorkflowStepType.BROWSER_NAVIGATE, params={"url": "about:blank"}, name="nav_blank"),
        WorkflowStep(type=WorkflowStepType.BROWSER_SEARCH, params={
            "query": "{{query}}", "engine": "google",
        }, name="search_web"),
        WorkflowStep(type=WorkflowStepType.BROWSER_EXTRACT, params={
            "selector": "p, h2, h3", "limit": 5,
        }, name="extract_results"),
        WorkflowStep(type=WorkflowStepType.THINK, params={"thought": "Synthesizing results..."}, name="think_synth"),
        WorkflowStep(type=WorkflowStepType.VOICE_SPEAK, params={
            "text": "{{summary}}", "async": False,
        }, name="speak_results"),
    ]
    engine.create_workflow("Browser Search and Speak", steps)
    print("  Workflow: Browser Search and Speak")


def _register_vision_analyze_report():
    steps = [
        WorkflowStep(type=WorkflowStepType.VISION_CAPTURE, params={"monitor": 1}, name="capture"),
        WorkflowStep(type=WorkflowStepType.VISION_ANALYZE, params={
            "detect_text": True, "detect_ui": True,
        }, name="analyze"),
        WorkflowStep(type=WorkflowStepType.THINK, params={"thought": "Analyzing screen contents..."}, name="think"),
        WorkflowStep(type=WorkflowStepType.NOTIFY, params={
            "message": "{{analysis_summary}}", "level": "info",
        }, name="notify"),
    ]
    engine.create_workflow("Vision Analyze and Report", steps)
    print("  Workflow: Vision Analyze and Report")


def _register_system_health_check():
    steps = [
        WorkflowStep(type=WorkflowStepType.SYSTEM_COMMAND, params={
            "command": "tasklist", "args": [],
        }, name="list_processes"),
        WorkflowStep(type=WorkflowStepType.THINK, params={
            "thought": "Checking system health...",
        }, name="think"),
        WorkflowStep(type=WorkflowStepType.SYSTEM_COMMAND, params={
            "command": "wmic os get FreePhysicalMemory,TotalVisibleMemorySize /Value",
        }, name="check_memory"),
        WorkflowStep(type=WorkflowStepType.VOICE_SPEAK, params={
            "text": "{{health_report}}", "async": True,
        }, name="speak_report"),
        WorkflowStep(type=WorkflowStepType.NOTIFY, params={
            "message": "{{health_report}}", "level": "info",
        }, name="log_report"),
    ]
    engine.create_workflow("System Health Check", steps)
    print("  Workflow: System Health Check")


def _register_voice_browser_chain():
    steps = [
        WorkflowStep(type=WorkflowStepType.VOICE_LISTEN, params={
            "timeout": 10.0, "language": "pt-BR",
        }, name="listen_query"),
        WorkflowStep(type=WorkflowStepType.THINK, params={
            "thought": "Processing voice query...",
        }, name="process_query"),
        WorkflowStep(type=WorkflowStepType.BROWSER_SEARCH, params={
            "query": "{{voice_query}}", "engine": "google",
        }, name="search"),
        WorkflowStep(type=WorkflowStepType.BROWSER_EXTRACT, params={
            "selector": "p", "limit": 3,
        }, name="extract"),
        WorkflowStep(type=WorkflowStepType.VOICE_SPEAK, params={
            "text": "{{search_results}}", "async": False,
        }, name="speak_answer"),
    ]
    engine.create_workflow("Voice -> Browser -> Speak", steps)
    print("  Workflow: Voice -> Browser -> Speak")


def _register_code_dev_loop():
    steps = [
        WorkflowStep(type=WorkflowStepType.THINK, params={
            "thought": "Starting code development loop...",
        }, name="init"),
        WorkflowStep(type=WorkflowStepType.SYSTEM_COMMAND, params={
            "command": "dir /b *.py", "cwd": "{{project_dir}}",
        }, name="list_files"),
        WorkflowStep(type=WorkflowStepType.SHELL_EXEC, params={
            "command": "git status --short", "cwd": "{{project_dir}}",
        }, name="git_status"),
        WorkflowStep(type=WorkflowStepType.CODE_GENERATE, params={
            "task": "{{dev_task}}",
        }, name="generate"),
        WorkflowStep(type=WorkflowStepType.CODE_EXECUTE, params={
            "file": "{{generated_file}}", "timeout": 30,
        }, name="test"),
        WorkflowStep(type=WorkflowStepType.VOICE_SPEAK, params={
            "text": "{{dev_summary}}", "async": True,
        }, name="speak_summary"),
    ]
    engine.create_workflow("Code Development Loop", steps)
    print("  Workflow: Code Development Loop")


def run_browser_search_speak(query: str):
    wf = engine.create_workflow(f"Search: {query[:30]}", [])
    wf.context["query"] = query
    wf.context["summary"] = ""
    wf.steps = [
        WorkflowStep(type=WorkflowStepType.BROWSER_NAVIGATE, params={"url": f"https://www.google.com/search?q={query}"}, name=f"search_{wf.workflow_id[:8]}"),
        WorkflowStep(type=WorkflowStepType.EXTRACT_TEXT, params={"selector": "body"}, name=f"extract_{wf.workflow_id[:8]}"),
        WorkflowStep(type=WorkflowStepType.THINK, params={"prompt": f"Summarize search results for: {query}"}, name=f"think_{wf.workflow_id[:8]}"),
        WorkflowStep(type=WorkflowStepType.VOICE_SPEAK, params={"text": "{{summary}}"}, name=f"speak_{wf.workflow_id[:8]}"),
    ]
    return wf


if __name__ == "__main__":
    register_builtin_workflows()
    print(f"\n  {len(engine.get_recent_workflows())} workflows registered")
