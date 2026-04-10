# ============================================================================
# ironframe/coordination/roles_v1_0.py - v1.0
# Last updated: 2026-04-07
# ============================================================================
# Component 14a: Role & Capability Registry
#
# Agents are registered with declared roles and capabilities before
# participating in task decomposition. An agent cannot accept assignments
# outside its declared role without escalation. Role boundary violations
# are anomalies.
# ============================================================================

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Agent types
ORCHESTRATOR = "orchestrator"
SPECIALIST = "specialist"
VALIDATOR = "validator"
TOOL_CALLER = "tool_caller"

AGENT_TYPES = [ORCHESTRATOR, SPECIALIST, VALIDATOR, TOOL_CALLER]


@dataclass
class AgentRole:
    """Declared role and capabilities for a participating agent."""
    agent_id: str
    agent_type: str              # orchestrator, specialist, validator, tool_caller
    autonomy_tier: int           # from C17 SessionToken (not self-declared)
    capabilities: List[str] = field(default_factory=list)
    allowed_task_types: List[str] = field(default_factory=list)
    resource_access: List[str] = field(default_factory=list)
    session_id: str = ""

    def can_handle(self, task_type: str) -> bool:
        """Check if this agent can handle a given task type."""
        if not self.allowed_task_types:
            return True  # empty = unrestricted within role
        return task_type in self.allowed_task_types

    def has_capability(self, capability: str) -> bool:
        return capability in self.capabilities

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "autonomy_tier": self.autonomy_tier,
            "capabilities": self.capabilities,
            "allowed_task_types": self.allowed_task_types,
        }


class RoleViolation(Exception):
    """Raised when an agent attempts action outside its declared role."""
    def __init__(self, agent_id: str, attempted: str, declared: str):
        self.agent_id = agent_id
        super().__init__(f"Role violation: agent '{agent_id}' attempted '{attempted}', declared role: '{declared}'")


class RoleRegistry:
    """Registry of participating agents with declared roles."""

    def __init__(self):
        self._agents: Dict[str, AgentRole] = {}

    def register(self, role: AgentRole) -> None:
        self._agents[role.agent_id] = role

    def get(self, agent_id: str) -> Optional[AgentRole]:
        return self._agents.get(agent_id)

    def unregister(self, agent_id: str) -> bool:
        if agent_id in self._agents:
            del self._agents[agent_id]
            return True
        return False

    def list_agents(self, agent_type: str = "") -> List[AgentRole]:
        if agent_type:
            return [a for a in self._agents.values() if a.agent_type == agent_type]
        return list(self._agents.values())

    def get_orchestrators(self) -> List[AgentRole]:
        return self.list_agents(ORCHESTRATOR)

    def check_assignment(self, agent_id: str, task_type: str) -> bool:
        """Check if agent can accept this task type. Returns False if violation."""
        role = self._agents.get(agent_id)
        if not role:
            return False
        return role.can_handle(task_type)

    def find_capable(self, capability: str) -> List[AgentRole]:
        """Find agents with a specific capability."""
        return [a for a in self._agents.values() if a.has_capability(capability)]

    def summary(self) -> Dict[str, Any]:
        by_type: Dict[str, int] = {}
        for agent in self._agents.values():
            by_type[agent.agent_type] = by_type.get(agent.agent_type, 0) + 1
        return {
            "total_agents": len(self._agents),
            "by_type": by_type,
        }
