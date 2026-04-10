# ============================================================================
# ironframe/agent_trust/identity_v1_0.py - v1.0
# Last updated: 2026-04-07
# ============================================================================
# Component 17a: Agent Identity & Attestation
#
# Session tokens are the SINGLE SOURCE OF TRUTH for role and autonomy tier.
# HMAC-SHA256 signed with local secret. No JWT dependency.
#
# Clarification: permissions_v1_0.py must always derive tier and role from
# a verified token, never from agent-provided values. Any agent self-declaring
# a higher tier is ignored and logged as anomaly.
# ============================================================================

import hashlib
import hmac
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from ironframe.agent_trust.tiers_v1_0 import AutonomyTier, tier_name


_DEFAULT_SECRET_ENV = "IRONFRAME_TOKEN_SECRET"
_DEFAULT_SESSION_TTL_MINUTES = 60


class TokenVerificationFailed(Exception):
    """Raised when a session token fails HMAC verification."""
    def __init__(self, reason: str):
        super().__init__(f"Token verification failed: {reason}")


class TokenExpired(Exception):
    """Raised when a session token has expired."""
    def __init__(self, session_id: str):
        super().__init__(f"Token expired for session {session_id}")


@dataclass
class SessionToken:
    """HMAC-signed session token. Single source of truth for agent identity.

    Non-transferable: tied to session_id. Privilege elevation requires
    new attestation event, not model assertion.
    """
    session_id: str
    agent_type: str
    role: str
    autonomy_tier: int
    issued_at: str
    expires_at: str
    scope: List[str] = field(default_factory=list)
    signature: str = ""

    def is_expired(self) -> bool:
        try:
            exp = datetime.fromisoformat(self.expires_at)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) >= exp
        except (ValueError, TypeError):
            return True

    def verify(self, secret: str) -> bool:
        """Verify HMAC signature. Returns True if valid."""
        expected = _compute_signature(self, secret)
        return hmac.compare_digest(self.signature, expected)

    @property
    def tier_name(self) -> str:
        return tier_name(self.autonomy_tier)

    def to_dict(self) -> Dict[str, Any]:
        """Safe serialization. Signature included for verification."""
        return {
            "session_id": self.session_id,
            "agent_type": self.agent_type,
            "role": self.role,
            "autonomy_tier": self.autonomy_tier,
            "tier_name": self.tier_name,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "scope": self.scope,
        }

    def to_signed_dict(self) -> Dict[str, Any]:
        d = self.to_dict()
        d["signature"] = self.signature
        return d


def _compute_signature(token: "SessionToken", secret: str) -> str:
    """Compute HMAC-SHA256 signature over token fields."""
    payload = json.dumps({
        "session_id": token.session_id,
        "agent_type": token.agent_type,
        "role": token.role,
        "autonomy_tier": token.autonomy_tier,
        "issued_at": token.issued_at,
        "expires_at": token.expires_at,
        "scope": sorted(token.scope),
    }, sort_keys=True, ensure_ascii=True)
    sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256)
    return sig.hexdigest()


class IdentityProvider:
    """Issues and verifies session tokens. Manages attestation events.

    The secret comes from env var IRONFRAME_TOKEN_SECRET. If not set,
    a random secret is generated per-process (acceptable for single-process v1).
    """

    def __init__(self, secret: Optional[str] = None,
                 session_ttl_minutes: int = _DEFAULT_SESSION_TTL_MINUTES,
                 audit_logger=None):
        self._secret = secret or os.environ.get(_DEFAULT_SECRET_ENV, "")
        if not self._secret:
            # Generate per-process secret if none configured
            self._secret = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
        self._ttl = session_ttl_minutes
        self._audit = audit_logger
        self._active_sessions: Dict[str, SessionToken] = {}

    def issue_token(
        self,
        agent_type: str,
        role: str,
        autonomy_tier: int = AutonomyTier.OBSERVE,
        scope: Optional[List[str]] = None,
        session_id: str = "",
    ) -> SessionToken:
        """Issue a new session token. Logs attestation event."""
        if not session_id:
            session_id = str(uuid.uuid4())[:12]

        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=self._ttl)

        token = SessionToken(
            session_id=session_id,
            agent_type=agent_type,
            role=role,
            autonomy_tier=autonomy_tier,
            issued_at=now.isoformat(),
            expires_at=expires.isoformat(),
            scope=scope or [],
        )
        token.signature = _compute_signature(token, self._secret)

        self._active_sessions[session_id] = token
        self._log_attestation("token_issued", token)
        return token

    def verify_token(self, token: SessionToken) -> SessionToken:
        """Verify a token's signature and expiry. Returns the token if valid.

        Raises TokenVerificationFailed or TokenExpired on failure.
        """
        if not token.verify(self._secret):
            self._log_attestation("verification_failed", token, detail="invalid_signature")
            raise TokenVerificationFailed("Invalid HMAC signature")

        if token.is_expired():
            self._log_attestation("verification_failed", token, detail="expired")
            raise TokenExpired(token.session_id)

        return token

    def elevate_tier(
        self,
        session_id: str,
        new_tier: int,
        approver: str = "",
    ) -> SessionToken:
        """Elevate autonomy tier for a session. Requires re-attestation.

        ELEVATED (Tier 4) requires explicit approver identity.
        This is the ONLY path to tier elevation — model assertions cannot self-elevate.
        """
        old_token = self._active_sessions.get(session_id)
        if not old_token:
            raise TokenVerificationFailed(f"No active session: {session_id}")

        if new_tier == AutonomyTier.ELEVATED and not approver:
            raise TokenVerificationFailed("ELEVATED tier requires explicit approver identity")

        # Issue new token with elevated tier
        new_token = self.issue_token(
            agent_type=old_token.agent_type,
            role=old_token.role,
            autonomy_tier=new_tier,
            scope=old_token.scope,
            session_id=session_id,
        )

        self._log_attestation("tier_elevated", new_token, detail=f"{old_token.autonomy_tier}->{new_tier}, approver={approver}")
        return new_token

    def downgrade_tier(self, session_id: str, new_tier: int, reason: str = "") -> SessionToken:
        """Downgrade autonomy tier. Used by anomaly detection."""
        old_token = self._active_sessions.get(session_id)
        if not old_token:
            raise TokenVerificationFailed(f"No active session: {session_id}")

        new_token = self.issue_token(
            agent_type=old_token.agent_type,
            role=old_token.role,
            autonomy_tier=new_tier,
            scope=old_token.scope,
            session_id=session_id,
        )

        self._log_attestation("tier_downgraded", new_token, detail=f"{old_token.autonomy_tier}->{new_tier}, reason={reason}")
        return new_token

    def revoke_session(self, session_id: str) -> bool:
        """Revoke a session token. Returns True if found."""
        token = self._active_sessions.pop(session_id, None)
        if token:
            self._log_attestation("session_revoked", token)
            return True
        return False

    def get_active_token(self, session_id: str) -> Optional[SessionToken]:
        """Get the current active token for a session."""
        return self._active_sessions.get(session_id)

    def active_session_count(self) -> int:
        return len(self._active_sessions)

    def _log_attestation(self, event: str, token: SessionToken, detail: str = "") -> None:
        if not self._audit:
            return
        try:
            self._audit.log_event(
                event_type=f"agent_trust.attestation.{event}",
                component="agent_trust.identity",
                session_id=token.session_id,
                details={
                    "agent_type": token.agent_type,
                    "role": token.role,
                    "autonomy_tier": token.autonomy_tier,
                    "tier_name": token.tier_name,
                    "detail": detail,
                },
            )
        except Exception:
            pass
