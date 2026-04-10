# ============================================================================
# ironframe/tool_governance/rate_limit_v1_0.py - v1.0
# Last updated: 2026-04-05
# ============================================================================
# Component 12e: Rate Limiting
#
# Three separate enforcement dimensions (correction #6):
#   1. RPM — sliding window requests per minute
#   2. Cost cap — daily cost accumulator per tool
#   3. Concurrency — max simultaneous calls per tool
#
# Follows BudgetTracker pattern from ironframe/mal/budget_v1_0.py.
# ============================================================================

import threading
import time
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List


class RateLimitExceeded(Exception):
    """Raised when a rate limit would be exceeded."""
    def __init__(self, tool_id: str, limit_type: str, detail: str):
        self.tool_id = tool_id
        self.limit_type = limit_type
        super().__init__(f"Rate limit exceeded for '{tool_id}': {limit_type} - {detail}")


@dataclass
class RateLimitPolicy:
    """Rate limit configuration for a tool (correction #6: explicit windows)."""
    rpm: int = 0                 # requests per minute (0 = unlimited)
    cost_cap_usd: float = 0.0   # per-day cost cap (0 = uncapped)
    concurrency: int = 0        # max simultaneous calls (0 = unlimited)


class ToolRateLimiter:
    """Per-tool rate limiting with RPM, daily cost, and concurrency.

    Thread-safe. Each tool tracked independently.
    """

    def __init__(self):
        self._lock = threading.Lock()
        # RPM tracking: tool_id -> list of timestamps
        self._rpm_windows: Dict[str, List[float]] = {}
        # Cost tracking: tool_id -> {date: total_cost}
        self._daily_cost: Dict[str, Dict[str, float]] = {}
        # Concurrency tracking: tool_id -> current count
        self._concurrent: Dict[str, int] = {}
        # Policies: tool_id -> RateLimitPolicy
        self._policies: Dict[str, RateLimitPolicy] = {}

    def set_policy(self, tool_id: str, policy: RateLimitPolicy) -> None:
        """Set rate limit policy for a tool."""
        with self._lock:
            self._policies[tool_id] = policy

    def check(self, tool_id: str, estimated_cost: float = 0.0) -> bool:
        """Check all rate limits before a call. Raises RateLimitExceeded if over.

        Call BEFORE executing. Returns True if OK.
        """
        with self._lock:
            policy = self._policies.get(tool_id)
            if not policy:
                return True  # no policy = no limits

            now = time.time()
            today = date.today().isoformat()

            # RPM check
            if policy.rpm > 0:
                window = self._rpm_windows.get(tool_id, [])
                cutoff = now - 60.0
                window = [t for t in window if t > cutoff]
                self._rpm_windows[tool_id] = window
                if len(window) >= policy.rpm:
                    raise RateLimitExceeded(
                        tool_id, "rpm",
                        f"{len(window)}/{policy.rpm} requests in last 60s"
                    )

            # Daily cost check
            if policy.cost_cap_usd > 0 and estimated_cost > 0:
                day_costs = self._daily_cost.get(tool_id, {})
                spent_today = day_costs.get(today, 0.0)
                if spent_today + estimated_cost > policy.cost_cap_usd:
                    raise RateLimitExceeded(
                        tool_id, "cost_cap",
                        f"${spent_today:.4f} + ${estimated_cost:.4f} exceeds daily cap ${policy.cost_cap_usd:.4f}"
                    )

            # Concurrency check
            if policy.concurrency > 0:
                current = self._concurrent.get(tool_id, 0)
                if current >= policy.concurrency:
                    raise RateLimitExceeded(
                        tool_id, "concurrency",
                        f"{current}/{policy.concurrency} concurrent calls"
                    )

        return True

    def acquire(self, tool_id: str) -> None:
        """Record start of a call. Increments RPM window and concurrency counter.

        Call AFTER check() passes, BEFORE execution.
        """
        with self._lock:
            # RPM
            if tool_id not in self._rpm_windows:
                self._rpm_windows[tool_id] = []
            self._rpm_windows[tool_id].append(time.time())

            # Concurrency
            self._concurrent[tool_id] = self._concurrent.get(tool_id, 0) + 1

    def release(self, tool_id: str, actual_cost: float = 0.0) -> None:
        """Record end of a call. Decrements concurrency, records cost.

        Call AFTER execution completes (success or failure).
        """
        with self._lock:
            # Concurrency
            current = self._concurrent.get(tool_id, 0)
            self._concurrent[tool_id] = max(0, current - 1)

            # Cost
            if actual_cost > 0:
                today = date.today().isoformat()
                if tool_id not in self._daily_cost:
                    self._daily_cost[tool_id] = {}
                self._daily_cost[tool_id][today] = (
                    self._daily_cost[tool_id].get(today, 0.0) + actual_cost
                )

    def remaining(self, tool_id: str) -> Dict[str, Any]:
        """Return remaining capacity for a tool."""
        with self._lock:
            policy = self._policies.get(tool_id)
            if not policy:
                return {"rpm": -1, "cost_cap": -1, "concurrency": -1}

            now = time.time()
            today = date.today().isoformat()

            # RPM remaining
            window = self._rpm_windows.get(tool_id, [])
            cutoff = now - 60.0
            recent = len([t for t in window if t > cutoff])
            rpm_remaining = max(0, policy.rpm - recent) if policy.rpm > 0 else -1

            # Cost remaining
            spent = self._daily_cost.get(tool_id, {}).get(today, 0.0)
            cost_remaining = max(0.0, policy.cost_cap_usd - spent) if policy.cost_cap_usd > 0 else -1

            # Concurrency remaining
            current = self._concurrent.get(tool_id, 0)
            conc_remaining = max(0, policy.concurrency - current) if policy.concurrency > 0 else -1

            return {
                "rpm": rpm_remaining,
                "cost_cap": round(cost_remaining, 6) if isinstance(cost_remaining, float) else cost_remaining,
                "concurrency": conc_remaining,
            }

    def summary(self) -> Dict[str, Any]:
        """Summary of all rate limit states."""
        with self._lock:
            return {
                "tools_tracked": len(self._policies),
                "active_concurrent": {
                    tid: count for tid, count in self._concurrent.items() if count > 0
                },
            }
