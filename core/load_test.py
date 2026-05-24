import asyncio
import sys
import time
sys.path.insert(0, '.')
from core.workflow_engine import WorkflowStepType, WorkflowStep, get_workflow_engine


async def run_load_test():
    engine = get_workflow_engine()
    workflows = []

    print("Creating 50 concurrent workflows...")
    for i in range(50):
        steps = [
            WorkflowStep(type=WorkflowStepType.WAIT, params={"duration": 0.05}, name=f"wait_{i}_1"),
            WorkflowStep(type=WorkflowStepType.NOTIFY, params={
                "message": f"Load test workflow {i}",
                "level": "info",
            }, name=f"notify_{i}"),
            WorkflowStep(type=WorkflowStepType.WAIT, params={"duration": 0.05}, name=f"wait_{i}_2"),
        ]
        wf = engine.create_workflow(f"load_test_{i}", steps, max_concurrency=10)
        workflows.append(wf)

    start = time.time()
    await asyncio.gather(*[engine.execute_workflow(wf) for wf in workflows])
    elapsed = time.time() - start

    completed = sum(1 for w in workflows if w.status.value == "completed")
    failed = sum(1 for w in workflows if w.status.value == "failed")

    print(f"\n  Load Test Results:")
    print(f"    Workflows: {len(workflows)}")
    print(f"    Completed: {completed}")
    print(f"    Failed:    {failed}")
    print(f"    Time:      {elapsed:.2f}s")
    print(f"    Throughput: {len(workflows)/elapsed:.1f} workflows/s")

    assert completed == 50, f"Expected 50 completed, got {completed}"
    return completed, failed, elapsed


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_load_test())
    finally:
        loop.close()
