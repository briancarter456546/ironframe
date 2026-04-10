# ============================================================================
# ironframe/budget/ledger_v1_0.py - v1.0
# Last updated: 2026-04-08
# ============================================================================
# Component 15b: Real-Time Budget Ledger
#
# Per-session running ledger tracking: token consumption, latency,
# tool call costs, and reliability overhead (hooks, schema, eval, audit).
# ============================================================================

import time
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ironframe.budget.profiles_v1_0 import TaskBudgetProfile, DEFAULT_PROFILE


# Ledger entry categories
MODEL_CALL = "model_call"
TOOL_CALL = "tool_call"
RELIABILITY_OVERHEAD = "reliability_overhead"  # hooks, schema checks, eval, audit


@dataclass
class LedgerEntry:
    """A single cost/latency event in the budget ledger."""
    timestamp: str
    category: str          # model_call, tool_call, reliability_overhead
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    model_id: str = ""
    tool_id: str = ""
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "category": self.category,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": round(self.cost_usd, 6),
            "latency_ms": round(self.latency_ms, 2),
            "model_id": self.model_id,
            "tool_id": self.tool_id,
        }


class BudgetLedger:
    """Per-session budget ledger. Thread-safe."""

    def __init__(self, profile: Optional[TaskBudgetProfile] = None):
        self._profile = profile or DEFAULT_PROFILE
        self._entries: List[LedgerEntry] = []
        self._start_time = time.time()
        self._lock = threading.Lock()

    @property
    def profile(self) -> TaskBudgetProfile:
        return self._profile

    def record(self, entry: LedgerEntry) -> None:
        """Record a ledger entry."""
        with self._lock:
            self._entries.append(entry)

    def record_model_call(self, tokens_in: int, tokens_out: int, cost_usd: float,
                           latency_ms: float, model_id: str = "") -> None:
        self.record(LedgerEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            category=MODEL_CALL,
            tokens_in=tokens_in, tokens_out=tokens_out,
            cost_usd=cost_usd, latency_ms=latency_ms, model_id=model_id,
        ))

    def record_tool_call(self, cost_usd: float, latency_ms: float,
                          tool_id: str = "") -> None:
        self.record(LedgerEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            category=TOOL_CALL,
            cost_usd=cost_usd, latency_ms=latency_ms, tool_id=tool_id,
        ))

    def record_overhead(self, cost_usd: float = 0.0, latency_ms: float = 0.0,
                         detail: str = "") -> None:
        """Record reliability overhead cost (hooks, schema, eval, audit)."""
        self.record(LedgerEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            category=RELIABILITY_OVERHEAD,
            cost_usd=cost_usd, latency_ms=latency_ms, detail=detail,
        ))

    # --- Aggregates ---

    @property
    def total_tokens(self) -> int:
        return sum(e.tokens_in + e.tokens_out for e in self._entries)

    @property
    def total_cost_usd(self) -> float:
        return sum(e.cost_usd for e in self._entries)

    @property
    def total_latency_ms(self) -> float:
        return sum(e.latency_ms for e in self._entries)

    @property
    def elapsed_ms(self) -> float:
        return (time.time() - self._start_time) * 1000

    @property
    def overhead_cost_usd(self) -> float:
        return sum(e.cost_usd for e in self._entries if e.category == RELIABILITY_OVERHEAD)

    @property
    def overhead_pct(self) -> float:
        total = self.total_cost_usd
        if total <= 0:
            return 0.0
        return self.overhead_cost_usd / total

    # --- Budget utilization ---

    def token_utilization(self) -> float:
        if self._profile.token_budget <= 0:
            return 0.0
        return self.total_tokens / self._profile.token_budget

    def cost_utilization(self) -> float:
        if self._profile.cost_ceiling_usd <= 0:
            return 0.0
        return self.total_cost_usd / self._profile.cost_ceiling_usd

    def latency_utilization(self) -> float:
        if self._profile.latency_sla_ms <= 0:
            return 0.0
        return self.elapsed_ms / self._profile.latency_sla_ms

    def by_category(self) -> Dict[str, Dict[str, float]]:
        """Breakdown by category."""
        cats: Dict[str, Dict[str, float]] = {}
        for e in self._entries:
            if e.category not in cats:
                cats[e.category] = {"cost_usd": 0.0, "latency_ms": 0.0, "tokens": 0, "count": 0}
            cats[e.category]["cost_usd"] += e.cost_usd
            cats[e.category]["latency_ms"] += e.latency_ms
            cats[e.category]["tokens"] += e.tokens_in + e.tokens_out
            cats[e.category]["count"] += 1
        return cats

    def summary(self) -> Dict[str, Any]:
        return {
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "elapsed_ms": round(self.elapsed_ms, 2),
            "token_utilization": round(self.token_utilization(), 4),
            "cost_utilization": round(self.cost_utilization(), 4),
            "latency_utilization": round(self.latency_utilization(), 4),
            "overhead_pct": round(self.overhead_pct, 4),
            "entry_count": len(self._entries),
            "by_category": self.by_category(),
        }
