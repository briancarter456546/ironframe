# ============================================================================
# ironframe/agent_trust/permissions_v1_0.py - v1.0
# Last updated: 2026-04-07
# ============================================================================
# Component 17d: JIT Least Privilege
#
# SINGLE AUTHORITY for all permission decisions. C4 and C12 MUST call into
# this module. No tool, KB write, or external call path may bypass it.
#
# Clarification: tier and role are ALWAYS derived from a verified
# SessionToken, never from agent-provided values or function arguments.
# Any agent self-declaring a higher tier is ignored and logged as anomaly.
# ============================================================================

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ironframe.agent_trust.identity_v1_0 import (
    SessionToken, IdentityProvider, TokenVerificationFailed, TokenExpired,
)
from ironframe.agent_trust.tiers_v1_0 import (
    AutonomyTier, get_tier_permissions, is_action_allowed, tier_name,
)
from ironframe.agent_trust.kill_switch_v1_0 import KillSwitch


@dataclass
class PermissionDecision:
    """Result of a permission check. This is what C4/C12 consume."""
    allowed: bool
    session_id: str
    action: str
    autonomy_tier: int
    tier_name: str
    denial_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "allowed": self.allowed,
            "session_id": self.session_id,
            "action": self.action,
            "autonomy_tier": self.autonomy_tier,
            "tier_name": self.tier_name,
        }
        if not self.allowed:
            d["denial_reason"] = self.denial_reason
        return d


class PermissionAuthority:
    """The SINGLE source of truth for whether an action is allowed.

    C4 (Hook Engine) and C12 (Tool Governance) call check_permission().
    They do NOT duplicate permission logic.

    All decisions derive tier from a verified SessionToken. Agent-provided
    tier values are rejected and logged as anomaly.
    """

    def __init__(
        self,
        identity_provider: IdentityProvider,
        kill_switch: KillSwitch,
        anomaly_detector=None,
        audit_logger=None,
    ):
        self._identity = identity_provider
        self._kill_switch = kill_switch
        self._anomaly = anomaly_detector
        self._audit = audit_logger

    def check_permission(
        self,
        session_id: str,
        action: str,
        target_class: str = "",
        claimed_tier: Optional[int] = None,
    ) -> PermissionDecision:
        """Check if an action is permitted for a session.

        This is the ONLY entry point for permission decisions.
        C4 and C12 call this. Nothing else decides permissions.

        Args:
            session_id: the session requesting the action
            action: one of read_kb, write_kb, canonical_write, tool_call, external_tool
            target_class: for write_kb, the target source class
            claimed_tier: if an agent provides this, it is IGNORED and logged as anomaly
        """
        # Step 1: Check kill switch FIRST — killed sessions cannot do anything
        if self._kill_switch.is_killed(session_id):
            return PermissionDecision(
                allowed=False, session_id=session_id, action=action,
                autonomy_tier=0, tier_name="KILLED",
                denial_reason="Session has been killed",
            )

        # Step 2: Get verified token — SINGLE SOURCE OF TRUTH for tier
        token = self._identity.get_active_token(session_id)
        if not token:
            return PermissionDecision(
                allowed=False, session_id=session_id, action=action,
                autonomy_tier=0, tier_name="NO_TOKEN",
                denial_reason="No active session token",
            )

        # Verify token is still valid
        try:
            self._identity.verify_token(token)
        except (TokenVerificationFailed, TokenExpired) as e:
            return PermissionDecision(
                allowed=False, session_id=session_id, action=action,
                autonomy_tier=token.autonomy_tier, tier_name=token.tier_name,
                denial_reason=str(e),
            )

        # Step 3: Check for self-elevation attempt
        # Clarification: if agent claims a tier different from token, log anomaly
        if claimed_tier is not None and claimed_tier != token.autonomy_tier:
            if claimed_tier > token.autonomy_tier:
                # Self-elevation attempt — ALWAYS anomalous
                if self._anomaly:
                    self._anomaly.observe_self_elevation_attempt(
                        session_id, claimed_tier, token.autonomy_tier
                    )
                self._log_permission("self_elevation_blocked", session_id, action,
                                     token.autonomy_tier, f"claimed={claimed_tier}, actual={token.autonomy_tier}")
            # Ignore claimed tier — use token tier

        # Step 4: Check quarantine on agent type
        if self._kill_switch.is_quarantined(token.agent_type):
            return PermissionDecision(
                allowed=False, session_id=session_id, action=action,
                autonomy_tier=token.autonomy_tier, tier_name=token.tier_name,
                denial_reason=f"Agent type '{token.agent_type}' is quarantined",
            )

        # Step 5: Check action against tier permissions
        actual_tier = token.autonomy_tier
        allowed = is_action_allowed(actual_tier, action, target_class)

        if not allowed:
            reason = f"Tier {tier_name(actual_tier)} does not permit '{action}'"
            if target_class:
                reason += f" on '{target_class}'"
            self._log_permission("denied", session_id, action, actual_tier, reason)
            return PermissionDecision(
                allowed=False, session_id=session_id, action=action,
                autonomy_tier=actual_tier, tier_name=tier_name(actual_tier),
                denial_reason=reason,
            )

        self._log_permission("allowed", session_id, action, actual_tier, "")
        return PermissionDecision(
            allowed=True, session_id=session_id, action=action,
            autonomy_tier=actual_tier, tier_name=tier_name(actual_tier),
        )

    def _log_permission(self, outcome: str, session_id: str, action: str,
                        tier: int, detail: str) -> None:
        if not self._audit:
            return
        try:
            self._audit.log_event(
                event_type=f"agent_trust.permission.{outcome}",
                component="agent_trust.permissions",
                session_id=session_id,
                details={
                    "action": action,
                    "autonomy_tier": tier,
                    "tier_name": tier_name(tier),
                    "detail": detail,
                },
            )
        except Exception:
            pass
