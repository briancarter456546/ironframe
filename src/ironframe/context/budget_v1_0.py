# ============================================================================
# ironframe/context/budget_v1_0.py - v1.0
# Last updated: 2026-04-06
# ============================================================================
# Component 9b: Token Budget Allocation
#
# Each zone has a declared token budget as percentage of total.
# Allocations configurable per skill. If CURRENT_TASK can't fit within
# its floor: escalate, never silently truncate.
# ============================================================================

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ironframe.context.zones_v1_0 import ContextZone, ZONE_SEQUENCE


class BudgetEscalation(Exception):
    """Raised when CURRENT_TASK cannot fit within its floor allocation."""
    def __init__(self, needed: int, available: int, total: int):
        self.needed = needed
        self.available = available
        super().__init__(
            f"CURRENT_TASK needs {needed} tokens but floor allows only {available} "
            f"of {total} total. Escalating — never silently truncate."
        )


# Default allocations (percentage of total budget)
_DEFAULT_ALLOCATIONS = {
    ContextZone.CONSTITUTIONAL: 0.10,
    ContextZone.CONTRACT: 0.08,
    ContextZone.TOOL_DEFINITIONS: 0.07,
    ContextZone.RETRIEVED_CONTEXT: 0.30,
    ContextZone.CONVERSATION_HISTORY: 0.25,
    ContextZone.CURRENT_TASK: 0.20,
}

# Hard floors (minimum percentage, cannot be compressed below)
_DEFAULT_FLOORS = {
    ContextZone.CONSTITUTIONAL: 0.05,
    ContextZone.CONTRACT: 0.04,
    ContextZone.TOOL_DEFINITIONS: 0.03,
    ContextZone.RETRIEVED_CONTEXT: 0.10,
    ContextZone.CONVERSATION_HISTORY: 0.05,
    ContextZone.CURRENT_TASK: 0.15,
}


@dataclass
class ZoneBudget:
    """Budget allocation for a single zone."""
    zone: str
    allocation_pct: float
    floor_pct: float
    max_tokens: int = 0        # computed from total
    floor_tokens: int = 0      # computed from total
    current_tokens: int = 0

    @property
    def over_budget(self) -> bool:
        return self.current_tokens > self.max_tokens

    @property
    def at_floor(self) -> bool:
        return self.current_tokens <= self.floor_tokens

    @property
    def tokens_over(self) -> int:
        return max(0, self.current_tokens - self.max_tokens)

    @property
    def compressible_tokens(self) -> int:
        """Tokens that can be removed before hitting the floor."""
        return max(0, self.current_tokens - self.floor_tokens)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "zone": self.zone,
            "allocation_pct": self.allocation_pct,
            "floor_pct": self.floor_pct,
            "max_tokens": self.max_tokens,
            "floor_tokens": self.floor_tokens,
            "current_tokens": self.current_tokens,
            "over_budget": self.over_budget,
            "at_floor": self.at_floor,
        }


class ContextBudgetAllocator:
    """Computes and enforces token budgets per zone.

    Total budget is set at assembly time (from model context window).
    Per-zone allocations are percentages. Configurable per skill.
    """

    def __init__(
        self,
        total_tokens: int = 128000,
        allocations: Optional[Dict[str, float]] = None,
        floors: Optional[Dict[str, float]] = None,
    ):
        self.total_tokens = total_tokens

        # Use defaults, allow overrides
        self._allocations = dict(_DEFAULT_ALLOCATIONS)
        if allocations:
            for zone_str, pct in allocations.items():
                zone = ContextZone(zone_str) if isinstance(zone_str, str) else zone_str
                self._allocations[zone] = pct

        self._floors = dict(_DEFAULT_FLOORS)
        if floors:
            for zone_str, pct in floors.items():
                zone = ContextZone(zone_str) if isinstance(zone_str, str) else zone_str
                self._floors[zone] = pct

        self._budgets: Dict[str, ZoneBudget] = {}
        self._compute_budgets()

    def _compute_budgets(self) -> None:
        """Compute token budgets from percentages."""
        self._budgets.clear()
        for zone in ZONE_SEQUENCE:
            alloc = self._allocations.get(zone, 0.10)
            floor = self._floors.get(zone, 0.05)
            self._budgets[zone.value] = ZoneBudget(
                zone=zone.value,
                allocation_pct=alloc,
                floor_pct=floor,
                max_tokens=int(self.total_tokens * alloc),
                floor_tokens=int(self.total_tokens * floor),
            )

    def get_budget(self, zone: str) -> ZoneBudget:
        """Get budget for a zone."""
        return self._budgets.get(zone, ZoneBudget(zone=zone, allocation_pct=0.0, floor_pct=0.0))

    def update_usage(self, zone: str, current_tokens: int) -> None:
        """Update current token count for a zone."""
        if zone in self._budgets:
            self._budgets[zone].current_tokens = current_tokens

    def check_current_task_floor(self, needed_tokens: int) -> None:
        """Check if CURRENT_TASK can fit. Raises BudgetEscalation if not.

        This is the escalation point — never silently truncate.
        """
        budget = self._budgets.get(ContextZone.CURRENT_TASK.value)
        if budget and needed_tokens > budget.floor_tokens:
            # Check if there's room after other zones
            used_by_others = sum(
                b.current_tokens for z, b in self._budgets.items()
                if z != ContextZone.CURRENT_TASK.value
            )
            available = self.total_tokens - used_by_others
            if needed_tokens > available:
                raise BudgetEscalation(needed_tokens, available, self.total_tokens)

    def over_budget_zones(self) -> List[str]:
        """Return zones that are over their allocation."""
        return [z for z, b in self._budgets.items() if b.over_budget]

    def total_used(self) -> int:
        return sum(b.current_tokens for b in self._budgets.values())

    def utilization(self) -> float:
        """Total budget utilization as fraction 0.0-1.0."""
        return self.total_used() / self.total_tokens if self.total_tokens > 0 else 0.0

    def summary(self) -> Dict[str, Any]:
        return {
            "total_tokens": self.total_tokens,
            "total_used": self.total_used(),
            "utilization": round(self.utilization(), 4),
            "zones": {z: b.to_dict() for z, b in self._budgets.items()},
            "over_budget": self.over_budget_zones(),
        }
