# ============================================================================
# ironframe/budget/manager_v1_0.py - v1.0
# Last updated: 2026-04-08
# ============================================================================
# Component 15 Orchestrator: CostLatencyManager
#
# Ties together profiles, ledger, SLA enforcement, routing signals,
# and telemetry. Provides unified interface for budget management.
#
# Coexists with mal/budget_v1_0.py (BudgetTracker handles MAL-level caps).
# C15 adds task-level profiles, SLA, and system-wide telemetry.
# ============================================================================

from typing import Any, Dict, List, Optional

from ironframe.budget.profiles_v1_0 import TaskBudgetProfile, ProfileRegistry, DEFAULT_PROFILE
from ironframe.budget.ledger_v1_0 import BudgetLedger
from ironframe.budget.sla_v1_0 import SLAEnforcer, SLACheck, BudgetCheck
from ironframe.budget.routing_v1_0 import RoutingSignal, generate_routing_signals
from ironframe.budget.telemetry_v1_0 import BudgetTelemetryEmitter, BudgetTelemetrySnapshot
from ironframe.audit.logger_v1_0 import AuditLogger


class SLABreach(Exception):
    """Raised when SLA is breached on a HARD enforcement profile."""
    def __init__(self, session_id: str, elapsed_ms: float, sla_ms: int):
        super().__init__(
            f"SLA breached: session {session_id}, elapsed {elapsed_ms:.0f}ms > SLA {sla_ms}ms"
        )


class CostLatencyManager:
    """Component 15 orchestrator.

    Manages per-session budget ledgers with task profiles, SLA enforcement,
    routing signals, and telemetry.
    """

    def __init__(self, audit_logger: Optional[AuditLogger] = None):
        self._audit = audit_logger
        self._profiles = ProfileRegistry()
        self._sla = SLAEnforcer()
        self._telemetry = BudgetTelemetryEmitter(audit_logger)
        self._sessions: Dict[str, BudgetLedger] = {}
        self._conformance_engine = None

    def register_conformance_engine(self, engine) -> None:
        """Register C18 ConformanceEngine to observe C15 SLA events."""
        self._conformance_engine = engine

    @property
    def profiles(self) -> ProfileRegistry:
        return self._profiles

    # --- Session lifecycle ---

    def start_session(self, session_id: str, task_type: str = "default") -> BudgetLedger:
        """Start a budget-tracked session with a task profile."""
        profile = self._profiles.get(task_type)
        ledger = BudgetLedger(profile)
        self._sessions[session_id] = ledger
        return ledger

    def get_ledger(self, session_id: str) -> Optional[BudgetLedger]:
        return self._sessions.get(session_id)

    def end_session(self, session_id: str) -> Optional[BudgetTelemetrySnapshot]:
        """End a session. Capture final telemetry. Returns snapshot."""
        ledger = self._sessions.pop(session_id, None)
        if not ledger:
            return None
        sla = self._sla.check_sla(ledger)
        return self._telemetry.capture(ledger, session_id, sla.status)

    # --- Recording ---

    def record_model_call(self, session_id: str, tokens_in: int, tokens_out: int,
                           cost_usd: float, latency_ms: float, model_id: str = "") -> None:
        ledger = self._sessions.get(session_id)
        if ledger:
            ledger.record_model_call(tokens_in, tokens_out, cost_usd, latency_ms, model_id)

    def record_tool_call(self, session_id: str, cost_usd: float,
                          latency_ms: float, tool_id: str = "") -> None:
        ledger = self._sessions.get(session_id)
        if ledger:
            ledger.record_tool_call(cost_usd, latency_ms, tool_id)

    def record_overhead(self, session_id: str, cost_usd: float = 0.0,
                         latency_ms: float = 0.0, detail: str = "") -> None:
        """Record reliability overhead (hooks, schema checks, eval, audit)."""
        ledger = self._sessions.get(session_id)
        if ledger:
            ledger.record_overhead(cost_usd, latency_ms, detail)

    # --- Budget & SLA checks ---

    def check_budget(self, session_id: str) -> Optional[BudgetCheck]:
        """Check current budget + SLA status. Returns None if session not found."""
        ledger = self._sessions.get(session_id)
        if not ledger:
            return None
        check = self._sla.check_budget(ledger)

        # Emit SLA events if status changed
        if check.sla_status != "normal":
            sla = self._sla.check_sla(ledger)
            self._telemetry.emit_sla_event(
                session_id, check.sla_status,
                f"Latency at {check.latency_utilization:.0%}",
                sla.skipped_controls,
            )

            # C15->C18 wiring: feed SLA event to conformance engine
            if self._conformance_engine is not None:
                try:
                    import uuid
                    from datetime import datetime, timezone
                    trace_event = {
                        "event_id": str(uuid.uuid4())[:12],
                        "event_type": "sla_violation",
                        "component_id": "C15",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "scope_id": session_id,
                        "sla_type": "latency",
                        "sla_threshold": ledger.profile.latency_sla_ms,
                        "actual_value": ledger.elapsed_ms,
                        "sla_status": check.sla_status,
                        "audit_logged": self._audit is not None,
                    }
                    self._conformance_engine.observe_event(trace_event)
                except Exception:
                    pass  # C18 observation must never break C15 operation

        # Check for hard breach
        if check.breach_flag and ledger.profile.enforcement == "HARD":
            raise SLABreach(session_id, ledger.elapsed_ms, ledger.profile.latency_sla_ms)

        return check

    def get_routing_signals(self, session_id: str) -> List[RoutingSignal]:
        """Get current routing signals for C1 (MAL). C15 signals, C1 routes."""
        check = self.check_budget(session_id)
        if not check:
            return []
        return generate_routing_signals(check)

    # --- Telemetry ---

    def capture_telemetry(self, session_id: str) -> Optional[BudgetTelemetrySnapshot]:
        """Capture current budget state as telemetry snapshot."""
        ledger = self._sessions.get(session_id)
        if not ledger:
            return None
        sla = self._sla.check_sla(ledger)
        return self._telemetry.capture(ledger, session_id, sla.status)

    def telemetry_summary(self) -> Dict[str, Any]:
        return self._telemetry.summary()

    def summary(self) -> Dict[str, Any]:
        return {
            "active_sessions": len(self._sessions),
            "profiles": self._profiles.summary(),
            "telemetry": self._telemetry.summary(),
        }
