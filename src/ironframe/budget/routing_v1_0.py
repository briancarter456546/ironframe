# ============================================================================
# ironframe/budget/routing_v1_0.py - v1.0
# Last updated: 2026-04-08
# ============================================================================
# Component 15c: Budget-Aware Routing Signals
#
# Generates signals for C1 (MAL) based on budget status. C15 signals,
# C1 routes. C15 never routes directly.
# ============================================================================

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ironframe.budget.sla_v1_0 import BudgetCheck


@dataclass
class RoutingSignal:
    """A routing preference signal for C1 (MAL)."""
    signal_type: str           # prefer_fast, prefer_cheap, prefer_efficient, block
    reason: str
    urgency: str = "normal"    # normal, high, critical

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_type": self.signal_type,
            "reason": self.reason,
            "urgency": self.urgency,
        }


def generate_routing_signals(budget_check: BudgetCheck) -> List[RoutingSignal]:
    """Translate budget status into routing signals for C1.

    C15 generates these signals. C1 (MAL) decides how to route.
    """
    signals = []

    if budget_check.hard_limit_reached:
        signals.append(RoutingSignal(
            signal_type="block",
            reason="Hard budget limit reached",
            urgency="critical",
        ))
        return signals  # no point adding preferences if blocked

    if "prefer_fast_model" in budget_check.signals:
        signals.append(RoutingSignal(
            signal_type="prefer_fast",
            reason=f"SLA at {budget_check.latency_utilization:.0%} — prioritize speed over accuracy",
            urgency="high",
        ))

    if "prefer_lower_cost_model" in budget_check.signals:
        signals.append(RoutingSignal(
            signal_type="prefer_cheap",
            reason=f"Cost at {budget_check.cost_utilization:.0%} — switch to lower-cost tier",
            urgency="high",
        ))

    if "prefer_token_efficient_model" in budget_check.signals:
        signals.append(RoutingSignal(
            signal_type="prefer_efficient",
            reason=f"Tokens at {budget_check.token_utilization:.0%} — switch to token-efficient tier",
            urgency="normal",
        ))

    return signals
