import asyncio
import logging
import time
from typing import Any, Optional

from agents.agent_base import AgentMessage, AgentStatus, BaseAgent
from core.event_bus import EventType, get_bus
from core.runtime import get_runtime

logger = logging.getLogger("orchestrator")


class OrchestratorAgent(BaseAgent):
    def __init__(self):
        super().__init__("orchestrator", "Orchestrates all agents and coordinates tasks")
        self._agents: dict[str, BaseAgent] = {}
        self._agent_priorities: dict[str, int] = {}
        self._message_routes: dict[str, list[str]] = {}
        self._task_assignments: dict[str, str] = {}

    def register_agent(self, agent: BaseAgent, priority: int = 0):
        self._agents[agent.name] = agent
        self._agent_priorities[agent.name] = priority
        logger.info(f"Orchestrator: Registered agent '{agent.name}'")

    def deregister_agent(self, agent_name: str):
        self._agents.pop(agent_name, None)
        self._agent_priorities.pop(agent_name, None)

    def add_route(self, from_agent: str, to_agent: str):
        if from_agent not in self._message_routes:
            self._message_routes[from_agent] = []
        self._message_routes[from_agent].append(to_agent)

    def get_agent(self, name: str) -> Optional[BaseAgent]:
        return self._agents.get(name)

    def get_agents_by_status(self, status: AgentStatus) -> list[BaseAgent]:
        return [a for a in self._agents.values() if a.status == status]

    async def think(self, context: dict) -> Optional[dict]:
        for agent in self._agents.values():
            if agent.status == AgentStatus.ERROR:
                logger.warning(f"Agent '{agent.name}' in error state. Attempting restart?")
        return {"action": "orchestrate", "agents_running": len(self._agents)}

    async def act(self, thought: dict) -> Any:
        return thought

    async def observe(self, event) -> Optional[dict]:
        event_type = event.type

        if event_type == EventType.AGENT_ERROR:
            agent_name = event.data.get("agent", "")
            self._bus.emit(EventType.SYSTEM_WARNING, {
                "message": f"Agent '{agent_name}' reported error",
                "details": event.data,
            }, source=self.name)

        return {"event": event_type.value, "handled": True}

    def route_message(self, msg: AgentMessage) -> Optional[str]:
        routes = self._message_routes.get(msg.source, [])
        for target in routes:
            target_agent = self._agents.get(target)
            if target_agent:
                target_agent.send_message(msg)
                return target
        return None

    def assign_task(self, task_id: str, agent_name: str) -> bool:
        if agent_name in self._agents:
            self._task_assignments[task_id] = agent_name
            return True
        return False

    def get_agent_for_task(self, task_type: str) -> Optional[str]:
        task_agent_map = {
            "coding": ["coding", "dev_agent"],
            "research": ["research", "web_search"],
            "browser": ["browser_agent"],
            "automation": ["automation_agent"],
            "vision": ["vision_agent"],
            "voice": ["voice_agent"],
            "memory": ["memory_agent"],
            "planning": ["planner_agent"],
            "gaming": ["gaming_agent"],
            "system": ["system_agent"],
        }
        candidates = task_agent_map.get(task_type, [])
        for name in candidates:
            if name in self._agents:
                return name
        return None

    def start_all_agents(self):
        sorted_agents = sorted(self._agents.items(), key=lambda x: -self._agent_priorities.get(x[0], 0))
        for name, agent in sorted_agents:
            try:
                agent.start()
            except Exception as e:
                logger.error(f"Failed to start agent '{name}': {e}")

    def stop_all_agents(self):
        for name, agent in self._agents.items():
            try:
                agent.stop()
            except Exception as e:
                logger.error(f"Failed to stop agent '{name}': {e}")

    def get_status_summary(self) -> dict:
        return {
            "total_agents": len(self._agents),
            "agents": {
                name: {
                    "status": agent.status.value,
                    "stats": agent.get_stats(),
                    "priority": self._agent_priorities.get(name, 0),
                }
                for name, agent in self._agents.items()
            },
            "routes": dict(self._message_routes),
            "active_tasks": len(self._task_assignments),
        }

    def __repr__(self):
        return f"OrchestratorAgent(agents={len(self._agents)}, running={len(self.get_agents_by_status(AgentStatus.RUNNING))})"
