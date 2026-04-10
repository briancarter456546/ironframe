# ============================================================================
# ironframe/tool_governance/auth_v1_0.py - v1.0
# Last updated: 2026-04-05
# ============================================================================
# Component 12b: Auth Lifecycle (JIT Credentials)
#
# Just-in-time credential injection. Credentials are:
#   - Scoped to execution context (not single-use per correction #4)
#   - Usable multiple times within context (retries, pagination)
#   - Revoked on release or failure
#   - NEVER in agent context, model context, audit log, or repr
#   - Usage count + last_used_at tracked and auditable
#
# Constitution: Law 3 (agents untrusted), dependency rule (12 is the
# only layer allowed to inject live credentials).
#
# v1 credential vault: os.environ.get(). HashiCorp Vault etc deferred.
# ============================================================================

import hashlib
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class CredentialRevoked(Exception):
    """Raised when attempting to use a revoked credential."""
    def __init__(self, credential_ref: str):
        super().__init__(f"Credential '{credential_ref}' has been revoked")


class CredentialNotFound(Exception):
    """Raised when the credential env var is not set."""
    def __init__(self, key: str):
        super().__init__(f"Credential key '{key}' not found in environment")


class JITCredential:
    """Opaque credential handle. The raw value is NEVER exposed in repr,
    serialization, or audit logs.

    Execution-context scoped: can be used multiple times until revoked.
    Usage count and timestamps are tracked for audit.
    """

    def __init__(self, credential_ref: str, tool_id: str, session_id: str,
                 credential_value: str):
        self.credential_ref = credential_ref  # redacted handle: "***_KEY_a1b2"
        self.tool_id = tool_id
        self.session_id = session_id
        self.issued_at = datetime.now(timezone.utc).isoformat()
        self._credential_value = credential_value  # PRIVATE
        self._revoked = False
        self._use_count = 0
        self._last_used_at = ""

    def use(self) -> str:
        """Get the raw credential value. Tracks usage.

        Can be called multiple times within execution context.
        Raises CredentialRevoked if revoked.
        """
        if self._revoked:
            raise CredentialRevoked(self.credential_ref)
        self._use_count += 1
        self._last_used_at = datetime.now(timezone.utc).isoformat()
        return self._credential_value

    def revoke(self) -> None:
        """Revoke this credential. Further use() calls will raise."""
        self._revoked = True
        self._credential_value = ""  # clear the value from memory

    @property
    def is_revoked(self) -> bool:
        return self._revoked

    @property
    def use_count(self) -> int:
        return self._use_count

    @property
    def last_used_at(self) -> str:
        return self._last_used_at

    def audit_summary(self) -> Dict[str, Any]:
        """Summary safe for audit logging. NEVER includes raw credential."""
        return {
            "credential_ref": self.credential_ref,
            "tool_id": self.tool_id,
            "session_id": self.session_id,
            "issued_at": self.issued_at,
            "revoked": self._revoked,
            "use_count": self._use_count,
            "last_used_at": self._last_used_at,
        }

    def __repr__(self) -> str:
        """NEVER includes _credential_value."""
        return (f"JITCredential(ref='{self.credential_ref}', tool='{self.tool_id}', "
                f"uses={self._use_count}, revoked={self._revoked})")

    def __str__(self) -> str:
        return self.__repr__()


class AuthLifecycle:
    """Manages JIT credential issuance, usage tracking, and revocation.

    Thread-safe. Tracks all issued credentials per session for cleanup.
    """

    def __init__(self):
        self._lock = threading.Lock()
        # session_id -> list of JITCredential
        self._active: Dict[str, List[JITCredential]] = {}

    def issue(
        self,
        tool_id: str,
        credential_key: str,
        session_id: str,
    ) -> JITCredential:
        """Issue a JIT credential for a tool call.

        Reads the credential from os.environ at call time.
        The raw value is wrapped in an opaque handle.
        """
        raw_value = os.environ.get(credential_key, "")
        if not raw_value:
            raise CredentialNotFound(credential_key)

        # Generate redacted ref: last 4 chars of hash
        ref_hash = hashlib.sha256(f"{tool_id}:{session_id}:{uuid.uuid4()}".encode()).hexdigest()[:4]
        credential_ref = f"***_{credential_key[-8:]}_{ref_hash}"

        credential = JITCredential(
            credential_ref=credential_ref,
            tool_id=tool_id,
            session_id=session_id,
            credential_value=raw_value,
        )

        with self._lock:
            if session_id not in self._active:
                self._active[session_id] = []
            self._active[session_id].append(credential)

        return credential

    def revoke(self, credential: JITCredential) -> None:
        """Revoke a specific credential."""
        credential.revoke()

    def revoke_all(self, session_id: str) -> int:
        """Revoke ALL credentials for a session. Returns count revoked.

        Critical for cleanup on session end or failure.
        """
        with self._lock:
            credentials = self._active.get(session_id, [])
            count = 0
            for cred in credentials:
                if not cred.is_revoked:
                    cred.revoke()
                    count += 1
            self._active.pop(session_id, None)
            return count

    def active_count(self, session_id: str = "") -> int:
        """Count active (non-revoked) credentials."""
        with self._lock:
            if session_id:
                return sum(1 for c in self._active.get(session_id, []) if not c.is_revoked)
            return sum(
                1 for creds in self._active.values()
                for c in creds if not c.is_revoked
            )

    def summary(self) -> Dict[str, Any]:
        """Summary for diagnostics. NEVER includes credential values."""
        with self._lock:
            total = sum(len(creds) for creds in self._active.values())
            active = sum(
                1 for creds in self._active.values()
                for c in creds if not c.is_revoked
            )
            return {
                "total_issued": total,
                "active": active,
                "sessions": len(self._active),
            }
