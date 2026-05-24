from agents.agent_base import AgentStatus, BaseAgent
from agents.orchestrator import OrchestratorAgent
from agents.observer_agent import ObserverAgent
from agents.reflection_agent import ReflectionAgent
from agents.continuous_loop import ContinuousLoop
from agents.vision_agent import VisionAgent, get_vision_agent
from agents.voice_agent import VoiceAgent, get_voice_agent
from agents.browser_agent_wrapper import BrowserAgentWrapper, get_browser_wrapper
from agents.self_repair_agent import SelfRepairAgent
from agents.research_agent import ResearchAgent, get_research_agent
from agents.coding_agent import CodingAgent, get_coding_agent
from agents.gaming_agent import GamingAgent, get_gaming_agent
from agents.system_agent import SystemAgent, get_system_agent


def create_default_orchestrator() -> OrchestratorAgent:
    orchestrator = OrchestratorAgent()
    orchestrator.register_agent(ObserverAgent(interval=5.0), priority=10)
    orchestrator.register_agent(ReflectionAgent(reflection_interval=60.0), priority=5)
    orchestrator.register_agent(VisionAgent(analyze_interval=10.0), priority=8)
    orchestrator.register_agent(SelfRepairAgent(repair_interval=120.0, auto_repair=True), priority=3)
    orchestrator.register_agent(ResearchAgent(analyze_interval=30.0), priority=7)
    orchestrator.register_agent(CodingAgent(), priority=6)
    orchestrator.register_agent(GamingAgent(), priority=4)
    orchestrator.register_agent(SystemAgent(monitor_interval=10.0), priority=5)
    return orchestrator
