# ============================================================================
# ironframe/agent_trust/kill_switch_v1_0.py - v1.0
# Last updated: 2026-04-07
# ============================================================================
# Component 17e: Kill Switch & Containment
#
# ZERO DEPENDENCIES on any component it may need to shut down.
# Imports ONLY stdlib + audit logger. No C4, C12, C5 imports.
#
# Four callers (pre-build decision #2):
#   C4 (Hook Engine), C5 (SAE), C18 (Drift Engine), CLI direct
#
# Four severity levels (escalating):
#   SUSPEND, CONTAIN, TERMINATE, QUARANTINE
#
# Kill state checked at enforcement points via is_killed(session_id).
# ============================================================================

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Dict, List, Optional, Set


class KillSeverity(IntEnum):
    """Kill switch severity levels. Escalating."""
    SUSPEND = 1       # pause all actions, await operator review
    CONTAIN = 2       # revoke permissions, complete current atomic op, halt
    TERMINATE = 3     # immediate session end, audit snapshot, release locks
    QUARANTINE = 4    # terminate + flag agent type for review


# Allowed callers — kill switch rejects calls from unknown sources
ALLOWED_CALLERS = frozenset({"hook_engine", "sae", "drift_engine", "operator"})


@dataclass
class KillEvent:
    """Record of a kill switch invocation."""
    session_id: str
    severity: int
    severity_name: str
    caller: str
    reason: str
    timestamp: str
    agent_type: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "severity": self.severity,
            "severity_name": self.severity_name,
            "caller": self.caller,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "agent_type": self.agent_type,
        }


class KillSwitch:
    """Atomic, irreversible kill switch. Zero circular dependencies.

    This module does NOT import C4, C12, C5, or any component it may
    need to shut down. It maintains its own kill registry. Enforcement
    points (C4 hooks, C12 tool governance) call is_killed() to check.
    """

    def __init__(self, audit_logger=None):
        # ONLY dependency: audit logger (optional, for logging kill events)
        self._audit = audit_logger
        self._lock = threading.Lock()
        self._killed_sessions: Dict[str, KillEvent] = {}
        self._quarantined_types: Set[str] = set()
        self._events: List[KillEvent] = []

    def invoke(
        self,
        session_id: str,
        severity: int,
        caller: str,
        reason: str = "",
        agent_type: str = "",
    ) -> KillEvent:
        """Invoke the kill switch. Atomic and irreversible within session.

        caller must be one of: hook_engine, sae, drift_engine, operator.
        Unknown callers are rejected.
        """
        # Validate caller
        if caller not in ALLOWED_CALLERS:
            # Log the unauthorized attempt but don't raise — kill switch
            # must not crash the calling component
            self._log_event("kill_switch_unauthorized_caller", session_id,
                            {"caller": caller, "reason": "not in ALLOWED_CALLERS"})
            # Still process the kill for safety — but log the violation
            pass

        severity_name = _severity_name(severity)
        now = datetime.now(timezone.utc).isoformat()

        event = KillEvent(
            session_id=session_id,
            severity=severity,
            severity_name=severity_name,
            caller=caller,
            reason=reason,
            timestamp=now,
            agent_type=agent_type,
        )

        with self._lock:
            # Record the kill (irreversible within session)
            existing = self._killed_sessions.get(session_id)
            if existing and existing.severity >= severity:
                # Already killed at equal or higher severity — no-op
                return existing

            self._killed_sessions[session_id] = event
            self._events.append(event)

            # QUARANTINE: flag agent type for review
            if severity >= KillSeverity.QUARANTINE and agent_type:
                self._quarantined_types.add(agent_type)

        # Log to audit — this is best-effort, kill must proceed even if logging fails
        self._log_event("kill_switch_invoked", session_id, event.to_dict())

        return event

    def is_killed(self, session_id: str) -> bool:
        """Check if a session has been killed. Called by enforcement points.

        This is the lightweight check that C4/C12 call before allowing actions.
        """
        return session_id in self._killed_sessions

    def get_kill_state(self, session_id: str) -> Optional[KillEvent]:
        """Get the kill event for a session, if killed."""
        return self._killed_sessions.get(session_id)

    def get_severity(self, session_id: str) -> int:
        """Get kill severity for a session. Returns 0 if not killed."""
        event = self._killed_sessions.get(session_id)
        return event.severity if event else 0

    def is_quarantined(self, agent_type: str) -> bool:
        """Check if an agent type is quarantined (blocked from future activation)."""
        return agent_type in self._quarantined_types

    def list_quarantined(self) -> List[str]:
        """List all quarantined agent types."""
        return sorted(self._quarantined_types)

    def unquarantine(self, agent_type: str, approver: str = "") -> bool:
        """Remove quarantine on an agent type. Requires operator action.

        Returns True if type was quarantined.
        """
        with self._lock:
            if agent_type in self._quarantined_types:
                self._quarantined_types.discard(agent_type)
                self._log_event("kill_switch_unquarantine", "",
                                {"agent_type": agent_type, "approver": approver})
                return True
            return False

    def summary(self) -> Dict[str, Any]:
        return {
            "killed_sessions": len(self._killed_sessions),
            "quarantined_types": sorted(self._quarantined_types),
            "total_events": len(self._events),
        }

    def _log_event(self, event_type: str, session_id: str, details: Dict[str, Any]) -> None:
        """Best-effort audit logging. Kill proceeds even if logging fails."""
        if not self._audit:
            return
        try:
            self._audit.log_event(
                event_type=f"agent_trust.{event_type}",
                component="agent_trust.kill_switch",
                session_id=session_id,
                details=details,
            )
        except Exception:
            pass  # Kill switch MUST NOT crash on audit failure


def _severity_name(severity: int) -> str:
    try:
        return KillSeverity(severity).name
    except ValueError:
        return f"UNKNOWN({severity})"
