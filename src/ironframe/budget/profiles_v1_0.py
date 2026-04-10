# ============================================================================
# ironframe/budget/profiles_v1_0.py - v1.0
# Last updated: 2026-04-08
# ============================================================================
# Component 15a: Task Budget Profiles
#
# Every task type has a declared budget profile: token budget, latency SLA,
# cost ceiling, enforcement tier. Tasks without profiles get a conservative
# system-wide default.
# ============================================================================

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class EnforcementTier(str, Enum):
    HARD = "HARD"       # block on breach
    SOFT = "SOFT"       # warn and degrade
    TRACK = "TRACK"     # observe only


@dataclass
class TaskBudgetProfile:
    """Budget profile for a task type."""
    profile_id: str
    task_type: str
    token_budget: int = 50000         # max input+output tokens
    latency_sla_ms: int = 30000       # 30s default
    cost_ceiling_usd: float = 1.0     # max dollar cost
    enforcement: str = EnforcementTier.SOFT.value
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "task_type": self.task_type,
            "token_budget": self.token_budget,
            "latency_sla_ms": self.latency_sla_ms,
            "cost_ceiling_usd": self.cost_ceiling_usd,
            "enforcement": self.enforcement,
        }


# System-wide conservative default
DEFAULT_PROFILE = TaskBudgetProfile(
    profile_id="default",
    task_type="default",
    token_budget=50000,
    latency_sla_ms=30000,
    cost_ceiling_usd=1.0,
    enforcement=EnforcementTier.SOFT.value,
    description="System-wide conservative default for tasks without declared profiles",
)


class ProfileRegistry:
    """Registry of task budget profiles."""

    def __init__(self):
        self._profiles: Dict[str, TaskBudgetProfile] = {"default": DEFAULT_PROFILE}

    def register(self, profile: TaskBudgetProfile) -> None:
        self._profiles[profile.task_type] = profile

    def get(self, task_type: str) -> TaskBudgetProfile:
        """Get profile for task type. Falls back to default."""
        return self._profiles.get(task_type, DEFAULT_PROFILE)

    def list_all(self) -> List[TaskBudgetProfile]:
        return list(self._profiles.values())

    def summary(self) -> Dict[str, Any]:
        return {
            "total_profiles": len(self._profiles),
            "task_types": list(self._profiles.keys()),
        }
