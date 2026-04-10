# ============================================================================
# ironframe/budget/sla_v1_0.py - v1.0
# Last updated: 2026-04-08
# ============================================================================
# Component 15d: SLA Enforcement
#
# Three thresholds:
#   Warning (60%): log warning, begin aggressive context compression
#   Degradation (80%): activate degraded mode, skip non-critical hooks
#   Breach (100%): halt task, emit SLA-breach event, return partial result
#
# Degraded mode is EXPLICIT — output tagged, audit records what was skipped.
# ============================================================================

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from ironframe.budget.ledger_v1_0 import BudgetLedger


class SLAStatus(str, Enum):
    NORMAL = "normal"
    WARNING = "warning"           # 60% elapsed
    DEGRADED = "degraded"         # 80% elapsed
    BREACHED = "breached"         # 100% elapsed


# Default thresholds as fraction of SLA
WARNING_THRESHOLD = 0.60
DEGRADATION_THRESHOLD = 0.80
BREACH_THRESHOLD = 1.00


@dataclass
class SLACheck:
    """Result of an SLA check."""
    status: str                    # SLAStatus value
    elapsed_ms: float
    sla_ms: int
    utilization: float             # 0.0-1.0+
    skipped_controls: List[str] = field(default_factory=list)
    breach_flag: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "sla_ms": self.sla_ms,
            "utilization": round(self.utilization, 4),
            "skipped_controls": self.skipped_controls,
            "breach_flag": self.breach_flag,
        }


@dataclass
class BudgetCheck:
    """Combined budget + SLA check result."""
    token_utilization: float
    cost_utilization: float
    latency_utilization: float
    sla_status: str
    hard_limit_reached: bool = False
    breach_flag: bool = False
    signals: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token_utilization": round(self.token_utilization, 4),
            "cost_utilization": round(self.cost_utilization, 4),
            "latency_utilization": round(self.latency_utilization, 4),
            "sla_status": self.sla_status,
            "hard_limit_reached": self.hard_limit_reached,
            "breach_flag": self.breach_flag,
            "signals": self.signals,
        }


class SLAEnforcer:
    """Enforces SLA thresholds and budget limits."""

    def __init__(
        self,
        warning_threshold: float = WARNING_THRESHOLD,
        degradation_threshold: float = DEGRADATION_THRESHOLD,
    ):
        self._warning = warning_threshold
        self._degradation = degradation_threshold

    def check_sla(self, ledger: BudgetLedger) -> SLACheck:
        """Check SLA status based on elapsed time."""
        elapsed = ledger.elapsed_ms
        sla_ms = ledger.profile.latency_sla_ms
        utilization = ledger.latency_utilization()

        if utilization >= BREACH_THRESHOLD:
            return SLACheck(
                status=SLAStatus.BREACHED.value,
                elapsed_ms=elapsed, sla_ms=sla_ms, utilization=utilization,
                breach_flag=True,
            )
        elif utilization >= self._degradation:
            return SLACheck(
                status=SLAStatus.DEGRADED.value,
                elapsed_ms=elapsed, sla_ms=sla_ms, utilization=utilization,
                skipped_controls=["non_critical_hooks", "verbose_schema_checks"],
            )
        elif utilization >= self._warning:
            return SLACheck(
                status=SLAStatus.WARNING.value,
                elapsed_ms=elapsed, sla_ms=sla_ms, utilization=utilization,
            )
        else:
            return SLACheck(
                status=SLAStatus.NORMAL.value,
                elapsed_ms=elapsed, sla_ms=sla_ms, utilization=utilization,
            )

    def check_budget(self, ledger: BudgetLedger) -> BudgetCheck:
        """Combined budget + SLA check with routing signals."""
        sla = self.check_sla(ledger)
        token_util = ledger.token_utilization()
        cost_util = ledger.cost_utilization()
        latency_util = ledger.latency_utilization()
        enforcement = ledger.profile.enforcement

        signals = []
        hard_limit = False

        # Token budget signals
        if token_util > 0.80:
            signals.append("prefer_token_efficient_model")
        if token_util >= 1.0 and enforcement == "HARD":
            signals.append("block_further_model_calls")
            hard_limit = True

        # Cost budget signals
        if cost_util > 0.80:
            signals.append("prefer_lower_cost_model")
        if cost_util >= 1.0 and enforcement == "HARD":
            signals.append("block_further_model_calls")
            hard_limit = True

        # Latency signals
        if latency_util > 0.70:
            signals.append("prefer_fast_model")

        return BudgetCheck(
            token_utilization=token_util,
            cost_utilization=cost_util,
            latency_utilization=latency_util,
            sla_status=sla.status,
            hard_limit_reached=hard_limit,
            breach_flag=sla.breach_flag,
            signals=signals,
        )
