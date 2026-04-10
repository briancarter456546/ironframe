# ============================================================================
# ironframe/context/telemetry_v1_0.py - v1.0
# Last updated: 2026-04-06
# ============================================================================
# Component 9g: Budget Telemetry
#
# Emits telemetry for every context package assembled. Consumed by
# C15 (cost accounting) and C18 (drift detection).
# ============================================================================

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ironframe.audit.logger_v1_0 import AuditLogger


@dataclass
class AssemblyTelemetry:
    """Telemetry for a single context assembly."""
    total_tokens: int = 0
    tokens_by_zone: Dict[str, int] = field(default_factory=dict)
    budget_utilization: float = 0.0
    compression_passes: int = 0
    tokens_saved: int = 0
    hard_truncations: int = 0
    trust_violations: int = 0
    context_rot_risk_score: float = 0.0
    context_rot_at_risk: bool = False
    escalated: bool = False
    assembly_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_tokens": self.total_tokens,
            "tokens_by_zone": self.tokens_by_zone,
            "budget_utilization": round(self.budget_utilization, 4),
            "compression_passes": self.compression_passes,
            "tokens_saved": self.tokens_saved,
            "hard_truncations": self.hard_truncations,
            "trust_violations": self.trust_violations,
            "context_rot_risk_score": round(self.context_rot_risk_score, 4),
            "context_rot_at_risk": self.context_rot_at_risk,
            "escalated": self.escalated,
            "assembly_time_ms": round(self.assembly_time_ms, 2),
        }


class ContextTelemetryEmitter:
    """Emits context budget telemetry to audit log."""

    def __init__(self, audit_logger: Optional[AuditLogger] = None):
        self._audit = audit_logger
        self._history: List[AssemblyTelemetry] = []

    def emit(self, telemetry: AssemblyTelemetry, session_id: str = "") -> None:
        """Log assembly telemetry to audit and internal history."""
        self._history.append(telemetry)

        if self._audit:
            try:
                self._audit.log_event(
                    event_type="context.budget.assembly",
                    component="context.manager",
                    session_id=session_id,
                    details=telemetry.to_dict(),
                )
            except Exception:
                pass

        # Emit specific events for notable conditions
        if telemetry.hard_truncations > 0 and self._audit:
            try:
                self._audit.log_event(
                    event_type="context.budget.hard_truncation",
                    component="context.manager",
                    session_id=session_id,
                    details={
                        "hard_truncations": telemetry.hard_truncations,
                        "tokens_saved": telemetry.tokens_saved,
                    },
                )
            except Exception:
                pass

        if telemetry.context_rot_at_risk and self._audit:
            try:
                self._audit.log_event(
                    event_type="context.budget.rot_risk",
                    component="context.manager",
                    session_id=session_id,
                    details={
                        "risk_score": telemetry.context_rot_risk_score,
                        "utilization": telemetry.budget_utilization,
                    },
                )
            except Exception:
                pass

    def recent(self, n: int = 10) -> List[Dict[str, Any]]:
        """Return recent telemetry entries."""
        return [t.to_dict() for t in self._history[-n:]]

    def summary(self) -> Dict[str, Any]:
        """Aggregate summary across all assemblies."""
        if not self._history:
            return {"assemblies": 0}
        return {
            "assemblies": len(self._history),
            "avg_utilization": round(
                sum(t.budget_utilization for t in self._history) / len(self._history), 4
            ),
            "total_tokens_saved": sum(t.tokens_saved for t in self._history),
            "total_hard_truncations": sum(t.hard_truncations for t in self._history),
            "total_trust_violations": sum(t.trust_violations for t in self._history),
            "rot_risk_events": sum(1 for t in self._history if t.context_rot_at_risk),
            "escalations": sum(1 for t in self._history if t.escalated),
        }
