# ============================================================================
# ironframe/conformance/runtime_monitor_v1_0.py - v1.0
# Last updated: 2026-04-08
# ============================================================================
# Component 18c: Runtime Conformance Monitor
#
# Non-blocking side-channel observer. Watches trace events and evaluates
# invariants from component contracts. Does NOT intercept the hot path.
#
# For each event:
#   1. Look up applicable invariants (by component_id + event_type)
#   2. Evaluate check against event payload
#   3. On failure: create DriftEvent
#
# May trigger downstream actions via registered callbacks.
# ============================================================================

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


# Drift types from the taxonomy
class DriftType(str, Enum):
    CODE_SPEC_MISMATCH = "CODE_SPEC_MISMATCH"
    ARCH_BOUNDARY_VIOLATION = "ARCH_BOUNDARY_VIOLATION"
    ORPHAN_ARTIFACT = "ORPHAN_ARTIFACT"
    INVARIANT_NOT_VERIFIED = "INVARIANT_NOT_VERIFIED"
    RTM_COVERAGE_GAP = "RTM_COVERAGE_GAP"
    PROTO_VIOLATION = "PROTO_VIOLATION"
    TRUST_ESCALATION = "TRUST_ESCALATION"
    LOCK_PRIORITY_VIOLATION = "LOCK_PRIORITY_VIOLATION"
    LOOP_HANDLING_FAILURE = "LOOP_HANDLING_FAILURE"
    AUDIT_GAP = "AUDIT_GAP"
    UNSPECIFIED_BEHAVIOR = "UNSPECIFIED_BEHAVIOR"


# Default severity and auto-action per drift type
DRIFT_DEFAULTS = {
    DriftType.CODE_SPEC_MISMATCH: {"severity": "warning", "auto_action": "alert"},
    DriftType.ARCH_BOUNDARY_VIOLATION: {"severity": "critical", "auto_action": "alert"},
    DriftType.ORPHAN_ARTIFACT: {"severity": "info", "auto_action": "none"},
    DriftType.INVARIANT_NOT_VERIFIED: {"severity": "warning", "auto_action": "alert"},
    DriftType.RTM_COVERAGE_GAP: {"severity": "warning", "auto_action": "alert"},
    DriftType.PROTO_VIOLATION: {"severity": "warning", "auto_action": "alert"},
    DriftType.TRUST_ESCALATION: {"severity": "critical", "auto_action": "kill"},
    DriftType.LOCK_PRIORITY_VIOLATION: {"severity": "warning", "auto_action": "alert"},
    DriftType.LOOP_HANDLING_FAILURE: {"severity": "critical", "auto_action": "alert"},
    DriftType.AUDIT_GAP: {"severity": "critical", "auto_action": "alert"},
    DriftType.UNSPECIFIED_BEHAVIOR: {"severity": "info", "auto_action": "none"},
}


@dataclass
class DriftEvent:
    """A detected deviation between spec and runtime behavior."""
    drift_event_id: str
    timestamp: str
    drift_type: str
    severity: str              # info, warning, critical
    description: str
    component_id: str = ""
    requirement_ids: List[str] = field(default_factory=list)
    invariant_ids: List[str] = field(default_factory=list)
    evidence_trace_ids: List[str] = field(default_factory=list)
    auto_action_taken: str = "none"    # none, alert, kill, rollback
    status: str = "open"               # open, acknowledged, mitigated
    baseline_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "drift_event_id": self.drift_event_id,
            "timestamp": self.timestamp,
            "drift_type": self.drift_type,
            "severity": self.severity,
            "description": self.description,
            "component_id": self.component_id,
            "requirement_ids": self.requirement_ids,
            "invariant_ids": self.invariant_ids,
            "evidence_trace_ids": self.evidence_trace_ids,
            "auto_action_taken": self.auto_action_taken,
            "status": self.status,
            "baseline_id": self.baseline_id,
        }


@dataclass
class Invariant:
    """A runtime invariant to monitor."""
    invariant_id: str
    description: str
    component_id: str
    event_types: List[str]     # which trace event types this applies to
    check_fn: Optional[Callable[[Dict[str, Any]], bool]] = None  # returns True if invariant holds
    drift_type: str = DriftType.PROTO_VIOLATION.value
    requirement_ids: List[str] = field(default_factory=list)


class RuntimeMonitor:
    """Non-blocking runtime conformance monitor.

    Evaluates invariants against incoming trace events.
    Does not intercept the hot path — observes only.
    """

    def __init__(self, audit_logger=None):
        self._audit = audit_logger
        self._invariants: List[Invariant] = []
        self._drift_events: List[DriftEvent] = []
        self._callbacks: Dict[str, List[Callable]] = {}  # drift_type -> [callback]
        self._event_count = 0

    def register_invariant(self, invariant: Invariant) -> None:
        """Register an invariant to monitor."""
        self._invariants.append(invariant)

    def register_callback(self, drift_type: str, callback: Callable[[DriftEvent], None]) -> None:
        """Register a callback for a drift type (e.g., kill switch for TRUST_ESCALATION)."""
        self._callbacks.setdefault(drift_type, []).append(callback)

    def observe(self, event: Dict[str, Any]) -> List[DriftEvent]:
        """Observe a trace event and evaluate applicable invariants.

        Returns list of new drift events (empty if all invariants hold).
        Non-blocking: exceptions in evaluation are caught and logged.
        """
        self._event_count += 1
        new_drifts = []
        event_type = event.get("event_type", "")
        component_id = event.get("component_id", "")

        for inv in self._invariants:
            # Check if this invariant applies to this event
            if event_type not in inv.event_types:
                continue

            # Evaluate the invariant
            try:
                if inv.check_fn:
                    holds = inv.check_fn(event)
                else:
                    holds = True  # no check function = passes

                if not holds:
                    drift = self._create_drift(inv, event)
                    new_drifts.append(drift)
                    self._drift_events.append(drift)
                    self._fire_callbacks(drift)
                    self._log_drift(drift)

            except Exception as exc:
                # Monitor must not crash — log and continue
                drift = DriftEvent(
                    drift_event_id=str(uuid.uuid4())[:12],
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    drift_type=DriftType.UNSPECIFIED_BEHAVIOR.value,
                    severity="warning",
                    description=f"Invariant {inv.invariant_id} evaluation error: {exc}",
                    component_id=component_id,
                    invariant_ids=[inv.invariant_id],
                )
                self._drift_events.append(drift)

        # Check for audit gap
        if event_type and not event.get("audit_logged", True):
            drift = DriftEvent(
                drift_event_id=str(uuid.uuid4())[:12],
                timestamp=datetime.now(timezone.utc).isoformat(),
                drift_type=DriftType.AUDIT_GAP.value,
                severity="critical",
                description=f"Event {event_type} has audit_logged=false",
                component_id=component_id,
                evidence_trace_ids=[event.get("event_id", "")],
            )
            new_drifts.append(drift)
            self._drift_events.append(drift)
            self._fire_callbacks(drift)

        return new_drifts

    def get_drift_events(self, drift_type: str = "", component_id: str = "",
                          status: str = "") -> List[DriftEvent]:
        """Query accumulated drift events."""
        results = self._drift_events
        if drift_type:
            results = [d for d in results if d.drift_type == drift_type]
        if component_id:
            results = [d for d in results if d.component_id == component_id]
        if status:
            results = [d for d in results if d.status == status]
        return results

    def acknowledge(self, drift_event_id: str) -> bool:
        """Acknowledge a drift event."""
        for d in self._drift_events:
            if d.drift_event_id == drift_event_id:
                d.status = "acknowledged"
                return True
        return False

    def mitigate(self, drift_event_id: str) -> bool:
        """Mark a drift event as mitigated."""
        for d in self._drift_events:
            if d.drift_event_id == drift_event_id:
                d.status = "mitigated"
                return True
        return False

    def _create_drift(self, inv: Invariant, event: Dict[str, Any]) -> DriftEvent:
        defaults = DRIFT_DEFAULTS.get(DriftType(inv.drift_type),
                                       {"severity": "warning", "auto_action": "none"})
        return DriftEvent(
            drift_event_id=str(uuid.uuid4())[:12],
            timestamp=datetime.now(timezone.utc).isoformat(),
            drift_type=inv.drift_type,
            severity=defaults["severity"],
            description=f"Invariant {inv.invariant_id} violated: {inv.description}",
            component_id=inv.component_id,
            requirement_ids=inv.requirement_ids,
            invariant_ids=[inv.invariant_id],
            evidence_trace_ids=[event.get("event_id", "")],
            auto_action_taken=defaults["auto_action"],
        )

    def _fire_callbacks(self, drift: DriftEvent) -> None:
        for cb in self._callbacks.get(drift.drift_type, []):
            try:
                cb(drift)
            except Exception:
                pass  # callbacks must not crash the monitor

    def _log_drift(self, drift: DriftEvent) -> None:
        if not self._audit:
            return
        try:
            self._audit.log_event(
                event_type="conformance.drift_detected",
                component="conformance.runtime_monitor",
                details=drift.to_dict(),
            )
        except Exception:
            pass

    def summary(self) -> Dict[str, Any]:
        by_type: Dict[str, int] = {}
        for d in self._drift_events:
            by_type[d.drift_type] = by_type.get(d.drift_type, 0) + 1
        return {
            "events_observed": self._event_count,
            "total_drifts": len(self._drift_events),
            "open_drifts": sum(1 for d in self._drift_events if d.status == "open"),
            "by_type": by_type,
            "invariants_registered": len(self._invariants),
        }


# ============================================================================
# Pre-built C14 invariant checks
# ============================================================================

def check_trust_escalation(event: Dict[str, Any]) -> bool:
    """INV-C14-TRUST-001: effective_tier must equal min(sender, receiver)."""
    effective = event.get("effective_tier", 0)
    sender = event.get("sender_trust_tier", 0)
    receiver = event.get("receiver_declared_tier", 0)
    expected = min(sender, receiver)
    return effective <= expected


def check_lock_priority(event: Dict[str, Any]) -> bool:
    """INV-C14-LOCK-001: resource granted by graph_priority then timestamp.

    If disposition is GRANTED, the queue_position should be 0 (first in queue).
    """
    disposition = event.get("disposition", "")
    if disposition != "GRANTED":
        return True  # only check grants
    queue_position = event.get("queue_position", 0)
    return queue_position == 0


def check_audit_logged(event: Dict[str, Any]) -> bool:
    """INV-C14-AUDIT-001: every coordination event must have audit_logged=true."""
    return event.get("audit_logged", False) is True


def register_c14_invariants(monitor: RuntimeMonitor) -> None:
    """Register all C14 invariants with the runtime monitor."""
    monitor.register_invariant(Invariant(
        invariant_id="INV-C14-TRUST-001",
        description="effective_tier == min(sender_tier, receiver_tier)",
        component_id="C14",
        event_types=["coordination_message"],
        check_fn=check_trust_escalation,
        drift_type=DriftType.TRUST_ESCALATION.value,
        requirement_ids=["IF-REQ-004A"],
    ))
    monitor.register_invariant(Invariant(
        invariant_id="INV-C14-LOCK-001",
        description="resource lock order by graph_priority then timestamp",
        component_id="C14",
        event_types=["resource_lock"],
        check_fn=check_lock_priority,
        drift_type=DriftType.LOCK_PRIORITY_VIOLATION.value,
        requirement_ids=["IF-REQ-004B"],
    ))
    monitor.register_invariant(Invariant(
        invariant_id="INV-C14-AUDIT-001",
        description="every coordination event audit_logged == true",
        component_id="C14",
        event_types=["coordination_message", "resource_lock", "loop_detected", "coordination_halt"],
        check_fn=check_audit_logged,
        drift_type=DriftType.AUDIT_GAP.value,
        requirement_ids=["IF-REQ-001"],
    ))
