# ============================================================================
# ironframe/budget/telemetry_v1_0.py - v1.0
# Last updated: 2026-04-08
# ============================================================================
# Component 15e: Budget Telemetry
#
# Aggregates cost/latency/token metrics per session and per task type.
# Feeds C7 audit and external monitoring. Makes reliability overhead visible.
# ============================================================================

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ironframe.audit.logger_v1_0 import AuditLogger
from ironframe.budget.ledger_v1_0 import BudgetLedger


@dataclass
class BudgetTelemetrySnapshot:
    """Point-in-time budget metrics snapshot."""
    session_id: str
    task_type: str
    total_tokens: int
    total_cost_usd: float
    elapsed_ms: float
    token_utilization: float
    cost_utilization: float
    latency_utilization: float
    overhead_pct: float
    entry_count: int
    sla_status: str = "normal"
    by_category: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "task_type": self.task_type,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "elapsed_ms": round(self.elapsed_ms, 2),
            "token_utilization": round(self.token_utilization, 4),
            "cost_utilization": round(self.cost_utilization, 4),
            "latency_utilization": round(self.latency_utilization, 4),
            "overhead_pct": round(self.overhead_pct, 4),
            "sla_status": self.sla_status,
            "by_category": self.by_category,
        }


class BudgetTelemetryEmitter:
    """Emits budget telemetry to C7 audit log."""

    def __init__(self, audit_logger: Optional[AuditLogger] = None):
        self._audit = audit_logger
        self._snapshots: List[BudgetTelemetrySnapshot] = []

    def capture(self, ledger: BudgetLedger, session_id: str = "",
                sla_status: str = "normal") -> BudgetTelemetrySnapshot:
        """Capture current budget state as a telemetry snapshot."""
        snap = BudgetTelemetrySnapshot(
            session_id=session_id,
            task_type=ledger.profile.task_type,
            total_tokens=ledger.total_tokens,
            total_cost_usd=ledger.total_cost_usd,
            elapsed_ms=ledger.elapsed_ms,
            token_utilization=ledger.token_utilization(),
            cost_utilization=ledger.cost_utilization(),
            latency_utilization=ledger.latency_utilization(),
            overhead_pct=ledger.overhead_pct,
            entry_count=len(ledger._entries),
            sla_status=sla_status,
            by_category=ledger.by_category(),
        )
        self._snapshots.append(snap)

        if self._audit:
            try:
                self._audit.log_event(
                    event_type="budget.telemetry",
                    component="budget.manager",
                    session_id=session_id,
                    details=snap.to_dict(),
                )
            except Exception:
                pass

        return snap

    def emit_sla_event(self, session_id: str, sla_status: str,
                        detail: str, skipped_controls: List[str] = None) -> None:
        """Emit SLA-specific event (warning, degradation, breach)."""
        if not self._audit:
            return
        try:
            self._audit.log_event(
                event_type=f"budget.sla.{sla_status}",
                component="budget.sla",
                session_id=session_id,
                details={
                    "sla_status": sla_status,
                    "detail": detail,
                    "skipped_controls": skipped_controls or [],
                },
            )
        except Exception:
            pass

    def recent(self, n: int = 10) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self._snapshots[-n:]]

    def summary(self) -> Dict[str, Any]:
        if not self._snapshots:
            return {"snapshots": 0}
        return {
            "snapshots": len(self._snapshots),
            "avg_cost": round(sum(s.total_cost_usd for s in self._snapshots) / len(self._snapshots), 6),
            "avg_overhead_pct": round(sum(s.overhead_pct for s in self._snapshots) / len(self._snapshots), 4),
        }
