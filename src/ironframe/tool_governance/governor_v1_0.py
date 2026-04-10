# ============================================================================
# ironframe/tool_governance/governor_v1_0.py - v1.0
# Last updated: 2026-04-05
# ============================================================================
# Component 12 Orchestrator: ToolGovernor
#
# 7-step governance flow with phase-specific audit events (correction #7).
# Ties together registry, versioning, auth, rate limits, contract validation,
# and resource locks. Cleanup invariant: try/finally ensures locks released
# and credentials revoked on any failure.
#
# C17/C18 stubs: degrade gracefully until those components are built.
# ============================================================================

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ironframe.tool_governance.registry_v1_0 import ToolRegistry, ToolDefinition
from ironframe.tool_governance.auth_v1_0 import AuthLifecycle, JITCredential
from ironframe.tool_governance.contract_v1_0 import ContractValidator
from ironframe.tool_governance.locks_v1_0 import ResourceLockManager, LockConflict
from ironframe.tool_governance.rate_limit_v1_0 import ToolRateLimiter, RateLimitPolicy, RateLimitExceeded
from ironframe.tool_governance.versioning_v1_0 import VersionGovernor
from ironframe.audit.logger_v1_0 import AuditLogger


@dataclass
class GovernanceDecision:
    """Result of the 7-step governance flow."""
    allowed: bool
    tool_id: str
    caller_id: str
    session_id: str
    version: str = ""
    denial_reason: str = ""
    denial_step: str = ""
    credential_ref: str = ""     # redacted handle ONLY, never raw value
    lock_id: str = ""
    validation_errors: List[Dict] = field(default_factory=list)

    # Internal refs for release() — not serialized
    _credential: Any = field(default=None, repr=False)
    _lock_resource: str = field(default="", repr=False)

    def to_dict(self) -> Dict[str, Any]:
        """Safe serialization. NEVER includes credential value."""
        d = {
            "allowed": self.allowed,
            "tool_id": self.tool_id,
            "caller_id": self.caller_id,
            "session_id": self.session_id,
            "version": self.version,
        }
        if not self.allowed:
            d["denial_reason"] = self.denial_reason
            d["denial_step"] = self.denial_step
        if self.credential_ref:
            d["credential_ref"] = self.credential_ref
        if self.lock_id:
            d["lock_id"] = self.lock_id
        if self.validation_errors:
            d["validation_errors"] = self.validation_errors
        return d


class ToolGovernor:
    """Orchestrates the 7-step tool governance flow.

    Every step emits a phase-specific audit event (correction #7).
    Cleanup invariant: locks and credentials are always cleaned up on failure.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        auth: AuthLifecycle,
        contract: ContractValidator,
        locks: ResourceLockManager,
        rate_limiter: ToolRateLimiter,
        versioning: VersionGovernor,
        audit_logger: Optional[AuditLogger] = None,
    ):
        self._registry = registry
        self._auth = auth
        self._contract = contract
        self._locks = locks
        self._rate_limiter = rate_limiter
        self._versioning = versioning
        self._audit = audit_logger

    def govern(
        self,
        tool_id: str,
        caller_id: str,
        session_id: str,
        params: Dict[str, Any],
        version: str = "",
        resource_id: str = "",
        caller_roles: Optional[List[str]] = None,
        caller_autonomy_tier: int = 0,
    ) -> GovernanceDecision:
        """Execute the 7-step governance flow.

        Returns GovernanceDecision. If allowed=True, caller may execute the tool.
        After execution, caller MUST call release().
        """
        credential = None
        lock_id = ""
        lock_resource = ""

        try:
            # --- Step 1: Registry Check ---
            tool = self._registry.get(tool_id)
            if not tool:
                self._emit("tool_governance.registry_check", session_id, {
                    "tool_id": tool_id, "outcome": "anomaly", "reason": "unregistered",
                })
                return self._deny(tool_id, caller_id, session_id, "Tool not registered", "registry_check")

            if not version:
                version = tool.version

            self._emit("tool_governance.registry_check", session_id, {
                "tool_id": tool_id, "outcome": "found", "risk": tool.risk,
            })

            # --- Step 2: Version Check ---
            version = self._versioning.resolve_version(tool_id, version)
            if not self._versioning.is_allowed(tool_id, version):
                self._emit("tool_governance.version_check", session_id, {
                    "tool_id": tool_id, "version": version, "outcome": "blocked_sunset",
                })
                return self._deny(tool_id, caller_id, session_id,
                                  f"Version {version} is past sunset", "version_check")

            deprecated = self._versioning.is_deprecated(tool_id, version)
            self._emit("tool_governance.version_check", session_id, {
                "tool_id": tool_id, "version": version,
                "outcome": "deprecated_warning" if deprecated else "allowed",
            })

            # --- Step 3: Caller Auth ---
            auth_ok = self._check_caller(tool, caller_id, caller_roles, caller_autonomy_tier)
            self._emit("tool_governance.auth_check", session_id, {
                "tool_id": tool_id, "caller_id": caller_id, "outcome": "allowed" if auth_ok else "denied",
            })
            if not auth_ok:
                return self._deny(tool_id, caller_id, session_id,
                                  "Caller not authorized", "auth_check")

            # --- Step 4: Rate Limit Check ---
            try:
                self._rate_limiter.check(tool_id)
                self._emit("tool_governance.rate_limit_check", session_id, {
                    "tool_id": tool_id, "outcome": "within_limits",
                })
            except RateLimitExceeded as e:
                self._emit("tool_governance.rate_limit_check", session_id, {
                    "tool_id": tool_id, "outcome": "exceeded", "limit_type": e.limit_type,
                })
                return self._deny(tool_id, caller_id, session_id,
                                  str(e), "rate_limit_check")

            # --- Step 5: Contract Validation (two layers) ---
            # Layer 2: per-tool payload schema
            vr = self._contract.validate_request(
                tool_id, params,
                governed=tool.governed,
                blocking=tool.blocking_validation,
            )
            self._emit("tool_governance.contract_validation", session_id, {
                "tool_id": tool_id, "outcome": vr.outcome,
                "error_count": len(vr.errors), "schema_id": vr.schema_id,
            })
            if not vr.valid and tool.blocking_validation:
                return self._deny(
                    tool_id, caller_id, session_id,
                    f"Contract validation failed: {vr.outcome}",
                    "contract_validation",
                    validation_errors=[e.to_dict() for e in vr.errors],
                )

            # --- Step 6: Resource Lock ---
            if resource_id:
                try:
                    lock_info = self._locks.acquire(resource_id, session_id, f"{tool_id}:{caller_id}")
                    lock_id = lock_info.lock_id
                    lock_resource = resource_id
                    self._emit("tool_governance.lock_acquire", session_id, {
                        "tool_id": tool_id, "resource_id": resource_id,
                        "lock_id": lock_id, "outcome": "acquired",
                    })
                except LockConflict as e:
                    self._emit("tool_governance.lock_acquire", session_id, {
                        "tool_id": tool_id, "resource_id": resource_id,
                        "outcome": "conflict", "held_by": e.held_by,
                    })
                    return self._deny(tool_id, caller_id, session_id,
                                      str(e), "lock_acquire")

            # --- Step 7: Credential Injection ---
            credential_ref = ""
            if tool.auth_required and tool.auth_credential_key:
                try:
                    credential = self._auth.issue(tool_id, tool.auth_credential_key, session_id)
                    credential_ref = credential.credential_ref
                    self._emit("tool_governance.credential_issue", session_id, {
                        "tool_id": tool_id, "credential_ref": credential_ref,
                        "outcome": "issued",
                    })
                except Exception as e:
                    # Credential failure: clean up lock if acquired
                    if lock_id:
                        self._locks.release(lock_id)
                    self._emit("tool_governance.credential_issue", session_id, {
                        "tool_id": tool_id, "outcome": "failed", "error": str(e),
                    })
                    return self._deny(tool_id, caller_id, session_id,
                                      f"Credential issue failed: {e}", "credential_issue")

            # --- Acquire rate limit slot ---
            self._rate_limiter.acquire(tool_id)

            return GovernanceDecision(
                allowed=True,
                tool_id=tool_id,
                caller_id=caller_id,
                session_id=session_id,
                version=version,
                credential_ref=credential_ref,
                lock_id=lock_id,
                _credential=credential,
                _lock_resource=lock_resource,
            )

        except Exception as exc:
            # Unexpected error: clean up any acquired resources
            if credential and not credential.is_revoked:
                credential.revoke()
            if lock_id:
                self._locks.release(lock_id)
            raise

    def release(
        self,
        decision: GovernanceDecision,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        actual_cost: float = 0.0,
    ) -> None:
        """Post-execution cleanup. MUST be called after govern() returns allowed=True.

        Validates response, revokes credential, releases lock, records rate usage, audits.
        """
        try:
            # Validate response if provided
            if result and decision.allowed:
                vr = self._contract.validate_response(
                    decision.tool_id, result,
                    governed=False,  # response validation is non-blocking by default
                )

            # Revoke credential
            if decision._credential and not decision._credential.is_revoked:
                self._emit("tool_governance.credential_issue", decision.session_id, {
                    "tool_id": decision.tool_id,
                    "credential_ref": decision.credential_ref,
                    "outcome": "revoked",
                    "use_count": decision._credential.use_count,
                })
                decision._credential.revoke()

            # Release lock
            if decision.lock_id:
                self._locks.release(decision.lock_id)

            # Record rate limit usage
            self._rate_limiter.release(decision.tool_id, actual_cost)

            # Final audit event
            self._emit("tool_governance.execution_release", decision.session_id, {
                "tool_id": decision.tool_id,
                "outcome": "error" if error else "success",
                "error": error or "",
                "actual_cost": actual_cost,
            })

        except Exception:
            # Cleanup must not crash — best effort
            if decision._credential and not decision._credential.is_revoked:
                decision._credential.revoke()
            if decision.lock_id:
                self._locks.release(decision.lock_id)
            if decision.tool_id:
                self._rate_limiter.release(decision.tool_id, actual_cost)

    def _check_caller(
        self,
        tool: ToolDefinition,
        caller_id: str,
        caller_roles: Optional[List[str]],
        caller_autonomy_tier: int,
    ) -> bool:
        """Check caller authorization against tool definition.

        Uses allowed_callers, allowed_roles, minimum_autonomy_tier.
        C17 stub: when Agent Trust is built, this will delegate to it.
        """
        # Explicit caller allowlist (override)
        if tool.allowed_callers:
            if caller_id not in tool.allowed_callers:
                return False

        # Role check (correction #2)
        if tool.allowed_roles and caller_roles:
            if not any(role in tool.allowed_roles for role in caller_roles):
                return False
        elif tool.allowed_roles and not caller_roles:
            return False  # roles required but none provided

        # Autonomy tier check (correction #2, stub for C17)
        if tool.minimum_autonomy_tier > 0:
            if caller_autonomy_tier < tool.minimum_autonomy_tier:
                return False

        return True

    def _deny(
        self,
        tool_id: str,
        caller_id: str,
        session_id: str,
        reason: str,
        step: str,
        validation_errors: Optional[List[Dict]] = None,
    ) -> GovernanceDecision:
        return GovernanceDecision(
            allowed=False,
            tool_id=tool_id,
            caller_id=caller_id,
            session_id=session_id,
            denial_reason=reason,
            denial_step=step,
            validation_errors=validation_errors or [],
        )

    def _emit(self, event_type: str, session_id: str, details: Dict[str, Any]) -> None:
        """Emit a phase-specific audit event (correction #7)."""
        if not self._audit:
            return
        try:
            self._audit.log_event(
                event_type=event_type,
                component="tool_governance.governor",
                session_id=session_id,
                details=details,
            )
        except Exception:
            pass  # audit must not crash governance
