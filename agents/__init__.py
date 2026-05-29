from agents.agent_base import AgentStatus, BaseAgent
from agents.orchestrator import OrchestratorAgent
from agents.continuous_loop import ContinuousLoop


def create_default_orchestrator() -> OrchestratorAgent:
    orchestrator = OrchestratorAgent()
    return orchestrator
