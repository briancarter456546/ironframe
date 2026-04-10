# ============================================================================
# ironframe/security/engine_v1_0.py - v1.0
# Last updated: 2026-04-05
# ============================================================================
# Component 11 Orchestrator: SecurityEngine
#
# Wires 11a-11e together. Registers a blocking pre_execution hook on C4
# at priority 10 (fires before domain hooks). Manages session-scoped
# content store for provenance tracking.
#
# Two main methods:
#   process_input() — full pipeline: tier -> scan -> sanitize -> log -> store
#   check_action()  — provenance chain -> gate decision
# ============================================================================

from typing import Any, Dict, List, Optional

from ironframe.security.trust_v1_0 import (
    TrustTier, TrustedContent, create_trusted_content, classify_trust_tier,
)
from ironframe.security.detection_v1_0 import scan_content, ScanResult, HOSTILE, DETECTED
from ironframe.security.sanitize_v1_0 import sanitize
from ironframe.security.gate_v1_0 import ActionGate, GateDecision, ProvenanceChain, build_provenance_chain
from ironframe.security.threat_log_v1_0 import ThreatEventLogger
from ironframe.tool_governance.registry_v1_0 import ToolRegistry
from ironframe.audit.logger_v1_0 import AuditLogger


class SecurityEngine:
    """Component 11 orchestrator. Wires trust tiering, injection detection,
    action gating, sanitization, and threat logging.

    Registers itself as a blocking hook on C4's pre_execution event.
    Maintains a session-scoped content store for provenance tracking.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        hook_engine=None,
        audit_logger: Optional[AuditLogger] = None,
    ):
        self._threat_log = ThreatEventLogger(audit_logger)
        self._gate = ActionGate(tool_registry, self._threat_log)
        self._tool_registry = tool_registry

        # Session-scoped content store for provenance tracking
        self._content_store: Dict[str, TrustedContent] = {}

        # Auto-register gate as blocking pre_execution hook
        if hook_engine:
            from ironframe.hooks.engine_v1_0 import HookResult
            hook_engine.register(
                "pre_execution",
                self._pre_execution_hook,
                name="security_gate",
                blocking=True,
                priority=10,
                description="Security action gate: provenance-based structural barrier",
            )

    def process_input(
        self,
        content: str,
        source: str,
        session_id: str,
        parent_content_ids: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TrustedContent:
        """Full security pipeline for incoming content.

        1. Classify trust tier (11a)
        2. Scan for injection (11b)
        3. Downgrade to HOSTILE if detected (11a)
        4. Sanitize by tier (11d)
        5. Log all events (11e)
        6. Store in content store for provenance
        7. Return TrustedContent
        """
        # Step 1: Create trusted content with initial tier
        tc = create_trusted_content(content, source, parent_content_ids, metadata)

        # Log tier assignment
        self._threat_log.log_tier_assignment(
            tc.content_id, tc.tier_name, source, session_id,
        )

        # Step 2: Scan for injection patterns (USER and EXTERNAL only)
        if tc.trust_tier <= TrustTier.USER:
            scan_result = scan_content(content, source)
            tc.detection_results = [scan_result.to_dict()]

            # Log scan
            self._threat_log.log_scan(
                tc.content_id, scan_result.to_dict(), tc.tier_name, source, session_id,
            )

            # Step 3: Downgrade if hostile
            if scan_result.threat_level in (HOSTILE, DETECTED):
                old_tier = tc.tier_name
                tc.downgrade_to(TrustTier.HOSTILE)
                self._threat_log.log_tier_downgrade(
                    tc.content_id, old_tier, "HOSTILE",
                    f"Injection detected: {scan_result.threat_level}", session_id,
                )
                self._threat_log.log_hostile(
                    tc.content_hash,
                    scan_result.to_dict().get("matched_rules", []),
                    source, session_id,
                )

        # Step 4: Sanitize by tier
        sanitized = sanitize(content, tc.trust_tier)
        tc.sanitized_content = sanitized.sanitized

        if sanitized.strips_applied:
            self._threat_log.log_sanitize(
                tc.content_id, tc.tier_name, sanitized.strips_applied, session_id,
            )

        # Step 5: Store for provenance tracking
        self._content_store[tc.content_id] = tc

        return tc

    def check_action(
        self,
        tool_id: str,
        input_content_ids: List[str],
        session_id: str = "",
    ) -> GateDecision:
        """Check whether a tool action is allowed given its input provenance.

        Builds a ProvenanceChain from stored content IDs and delegates
        to the ActionGate (11c).
        """
        provenance = build_provenance_chain(input_content_ids, self._content_store)
        return self._gate.check(tool_id, provenance, session_id)

    def get_content(self, content_id: str) -> Optional[TrustedContent]:
        """Retrieve a stored content item by ID."""
        return self._content_store.get(content_id)

    def clear_session(self, session_id: str = "") -> int:
        """Clear stored content. Returns count cleared.

        If session_id given, clears only that session's content.
        If empty, clears everything.
        """
        if not session_id:
            count = len(self._content_store)
            self._content_store.clear()
            return count
        to_clear = [cid for cid, tc in self._content_store.items()
                     if tc.metadata.get("session_id") == session_id]
        for cid in to_clear:
            del self._content_store[cid]
        return len(to_clear)

    def _pre_execution_hook(self, event: Dict[str, Any]):
        """Hook handler registered on C4's pre_execution event.

        Extracts tool_id and input_content_ids from the event context.
        Returns HookResult(allow=True/False).
        """
        from ironframe.hooks.engine_v1_0 import HookResult

        tool_id = event.get("tool_id", "")
        input_ids = event.get("input_content_ids", [])
        session_id = event.get("session_id", "")

        # If no tool_id or no tracked inputs, allow (no gate check needed)
        if not tool_id or not input_ids:
            return HookResult(allow=True, message="No security gate check required")

        decision = self.check_action(tool_id, input_ids, session_id)

        if decision.allowed:
            return HookResult(allow=True, metadata={"gate_action": "allow"})

        return HookResult(
            allow=False,
            message=decision.denial_reason,
            metadata={
                "gate_action": decision.action,
                "tool_risk": decision.tool_risk,
                "lowest_tier": decision.lowest_input_tier,
                "requires_confirmation": decision.requires_confirmation,
            },
        )

    def summary(self) -> Dict[str, Any]:
        """Diagnostic summary."""
        tier_counts: Dict[str, int] = {}
        for tc in self._content_store.values():
            name = tc.tier_name
            tier_counts[name] = tier_counts.get(name, 0) + 1
        return {
            "content_tracked": len(self._content_store),
            "by_tier": tier_counts,
        }
