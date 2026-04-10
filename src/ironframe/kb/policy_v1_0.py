# ============================================================================
# ironframe/kb/policy_v1_0.py - v1.0
# Last updated: 2026-04-06
# ============================================================================
# Component 10g: Retrieval Policy Enforcement
#
# Governs what source classes are accessible per task context:
#   - Governed tasks: Canonical + Authoritative Domain only
#   - Standard tasks: all source classes, weighted by class
#   - Agent-initiated: scoped by autonomy tier (C17 stub)
#
# Retrieval scope violations (grounding governed claim from Analytical/Ephemeral)
# are logged as policy violations.
# ============================================================================

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ironframe.audit.logger_v1_0 import AuditLogger


# Source classes permitted per task scope
_GOVERNED_CLASSES = ["canonical", "authoritative_domain"]
_STANDARD_CLASSES = ["canonical", "authoritative_domain", "analytical", "ephemeral"]

# C17 stub: autonomy tier -> allowed source classes
# Lower tier agents get narrower scope
_TIER_SCOPE = {
    0: ["canonical", "authoritative_domain"],               # untrusted agents
    1: ["canonical", "authoritative_domain"],               # basic agents
    2: ["canonical", "authoritative_domain", "analytical"], # intermediate
    3: _STANDARD_CLASSES,                                    # trusted
    4: _STANDARD_CLASSES,                                    # fully trusted
}


@dataclass
class RetrievalPolicy:
    """Policy for a retrieval operation."""
    governed: bool = False
    allowed_classes: List[str] = None
    agent_autonomy_tier: int = 4     # default: fully trusted (C17 stub)

    def __post_init__(self):
        if self.allowed_classes is None:
            if self.governed:
                self.allowed_classes = list(_GOVERNED_CLASSES)
            else:
                tier_classes = _TIER_SCOPE.get(self.agent_autonomy_tier, _STANDARD_CLASSES)
                self.allowed_classes = list(tier_classes)


@dataclass
class PolicyViolation:
    """A retrieval scope violation."""
    violation_type: str    # "governed_scope_breach", "tier_scope_breach"
    attempted_class: str
    allowed_classes: List[str]
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "violation_type": self.violation_type,
            "attempted_class": self.attempted_class,
            "allowed_classes": self.allowed_classes,
            "detail": self.detail,
        }


class RetrievalPolicyEnforcer:
    """Enforces retrieval scope restrictions per task context."""

    def __init__(self, audit_logger: Optional[AuditLogger] = None):
        self._audit = audit_logger

    def get_policy(
        self,
        governed: bool = False,
        agent_autonomy_tier: int = 4,
    ) -> RetrievalPolicy:
        """Build a retrieval policy for the current task context."""
        return RetrievalPolicy(
            governed=governed,
            agent_autonomy_tier=agent_autonomy_tier,
        )

    def check_scope(
        self,
        policy: RetrievalPolicy,
        result_source_classes: List[str],
        session_id: str = "",
    ) -> List[PolicyViolation]:
        """Check if retrieval results respect the policy scope.

        Returns list of violations (empty = compliant).
        Violations are logged to C7 audit.
        """
        violations = []

        for sc in result_source_classes:
            if sc not in policy.allowed_classes:
                vtype = "governed_scope_breach" if policy.governed else "tier_scope_breach"
                violation = PolicyViolation(
                    violation_type=vtype,
                    attempted_class=sc,
                    allowed_classes=policy.allowed_classes,
                    detail=f"Source class '{sc}' not permitted under current policy "
                           f"({'governed' if policy.governed else f'tier {policy.agent_autonomy_tier}'})",
                )
                violations.append(violation)
                self._log_violation(violation, session_id)

        return violations

    def filter_by_policy(
        self,
        chunks: List[Dict[str, Any]],
        policy: RetrievalPolicy,
    ) -> List[Dict[str, Any]]:
        """Filter retrieval results to only permitted source classes."""
        return [c for c in chunks if c.get("source_class", "") in policy.allowed_classes]

    def _log_violation(self, violation: PolicyViolation, session_id: str) -> None:
        if not self._audit:
            return
        try:
            self._audit.log_event(
                event_type="kb.policy_violation",
                component="kb.policy",
                session_id=session_id,
                details=violation.to_dict(),
            )
        except Exception:
            pass
