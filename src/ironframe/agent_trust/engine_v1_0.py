# ============================================================================
# ironframe/agent_trust/engine_v1_0.py - v1.0
# Last updated: 2026-04-07
# ============================================================================
# Component 17 Orchestrator: AgentTrustEngine
#
# Ties together identity, tiers, permissions, anomaly detection, kill switch,
# and provenance tagging. Provides the unified interface that C4 and C12
# call through permissions_v1_0.py (the single authority).
# ============================================================================

from typing import Any, Dict, List, Optional

from ironframe.agent_trust.tiers_v1_0 import AutonomyTier
from ironframe.agent_trust.identity_v1_0 import IdentityProvider, SessionToken
from ironframe.agent_trust.kill_switch_v1_0 import KillSwitch, KillSeverity
from ironframe.agent_trust.anomaly_v1_0 import AnomalyDetector, AnomalyAssessment, AgentBaseline, CRITICAL_THRESHOLD
from ironframe.agent_trust.permissions_v1_0 import PermissionAuthority, PermissionDecision
from ironframe.agent_trust.provenance_v1_0 import OutputProvenance, create_provenance
from ironframe.audit.logger_v1_0 import AuditLogger


class AgentTrustEngine:
    """Component 17 orchestrator.

    Provides session lifecycle management, permission checking (single authority),
    anomaly assessment, kill switch, and provenance tagging.
    """

    def __init__(self, audit_logger: Optional[AuditLogger] = None,
                 token_secret: str = ""):
        self._audit = audit_logger
        self._identity = IdentityProvider(secret=token_secret, audit_logger=audit_logger)
        self._kill_switch = KillSwitch(audit_logger=audit_logger)
        self._anomaly = AnomalyDetector()
        self._permissions = PermissionAuthority(
            identity_provider=self._identity,
            kill_switch=self._kill_switch,
            anomaly_detector=self._anomaly,
            audit_logger=audit_logger,
        )
        # Track downgrades per session for provenance
        self._session_downgrades: Dict[str, List[str]] = {}

    # --- Properties for C4/C12 integration ---

    @property
    def permissions(self) -> PermissionAuthority:
        """The single permission authority. C4 and C12 call this."""
        return self._permissions

    @property
    def kill_switch(self) -> KillSwitch:
        """Kill switch. Callable by C4, C5, C18, operator."""
        return self._kill_switch

    @property
    def anomaly_detector(self) -> AnomalyDetector:
        return self._anomaly

    @property
    def identity(self) -> IdentityProvider:
        return self._identity

    # --- Session lifecycle ---

    def start_session(
        self,
        agent_type: str,
        role: str,
        autonomy_tier: int = AutonomyTier.OBSERVE,
        scope: Optional[List[str]] = None,
    ) -> SessionToken:
        """Start a new agent session. Issues a signed token."""
        # Check quarantine before allowing session start
        if self._kill_switch.is_quarantined(agent_type):
            raise ValueError(f"Agent type '{agent_type}' is quarantined. Cannot start session.")

        token = self._identity.issue_token(
            agent_type=agent_type,
            role=role,
            autonomy_tier=autonomy_tier,
            scope=scope,
        )
        self._session_downgrades[token.session_id] = []
        return token

    def end_session(self, session_id: str) -> None:
        """End a session. Revokes token, clears anomaly observations."""
        self._identity.revoke_session(session_id)
        self._anomaly.clear_session(session_id)
        self._session_downgrades.pop(session_id, None)

    # --- Permission checking (delegates to single authority) ---

    def check_permission(self, session_id: str, action: str,
                         target_class: str = "", claimed_tier: Optional[int] = None) -> PermissionDecision:
        """Check if action is allowed. THE entry point for C4/C12."""
        return self._permissions.check_permission(session_id, action, target_class, claimed_tier)

    # --- Anomaly & tier management ---

    def assess_anomaly(self, session_id: str) -> AnomalyAssessment:
        """Run anomaly assessment for a session. May trigger tier downgrade or kill."""
        token = self._identity.get_active_token(session_id)
        if not token:
            return AnomalyAssessment(session_id=session_id, agent_type="unknown", score=0.0)

        assessment = self._anomaly.assess(session_id, token.agent_type)

        # Auto-downgrade if recommended
        if assessment.tier_downgrade_recommended and assessment.recommended_tier > 0:
            if assessment.recommended_tier < token.autonomy_tier:
                self._identity.downgrade_tier(
                    session_id, assessment.recommended_tier,
                    reason=f"anomaly_score={assessment.score:.2f}"
                )
                self._session_downgrades.setdefault(session_id, []).append(
                    f"T{token.autonomy_tier}->T{assessment.recommended_tier} (anomaly={assessment.score:.2f})"
                )

        # Auto-kill if critical
        if assessment.score >= CRITICAL_THRESHOLD:
            self._kill_switch.invoke(
                session_id=session_id,
                severity=KillSeverity.CONTAIN,
                caller="sae",  # anomaly detection is a SAE-adjacent function
                reason=f"Critical anomaly score: {assessment.score:.2f}",
                agent_type=token.agent_type,
            )

        return assessment

    def elevate_tier(self, session_id: str, new_tier: int, approver: str = "") -> SessionToken:
        """Elevate a session's autonomy tier. Requires re-attestation."""
        return self._identity.elevate_tier(session_id, new_tier, approver)

    # --- Provenance ---

    def create_output_provenance(
        self,
        session_id: str,
        kb_entities: Optional[List[str]] = None,
        tool_calls: Optional[List[str]] = None,
    ) -> OutputProvenance:
        """Create a provenance tag for an agent output."""
        token = self._identity.get_active_token(session_id)
        if not token:
            return create_provenance(
                session_id=session_id, agent_type="unknown",
                autonomy_tier=0, anomaly_score=1.0,
            )

        assessment = self._anomaly.assess(session_id, token.agent_type)
        downgrades = self._session_downgrades.get(session_id, [])

        return create_provenance(
            session_id=session_id,
            agent_type=token.agent_type,
            autonomy_tier=token.autonomy_tier,
            agent_id=token.session_id,
            kb_entities=kb_entities,
            tool_calls=tool_calls,
            anomaly_score=assessment.score,
            tier_downgrades=downgrades,
        )

    # --- Registration ---

    def register_baseline(self, baseline: AgentBaseline) -> None:
        """Register a behavioral baseline for an agent type."""
        self._anomaly.register_baseline(baseline)

    # --- Diagnostics ---

    def summary(self) -> Dict[str, Any]:
        return {
            "active_sessions": self._identity.active_session_count(),
            "kill_switch": self._kill_switch.summary(),
        }
