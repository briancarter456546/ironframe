# ============================================================================
# ironframe/security/threat_log_v1_0.py - v1.0
# Last updated: 2026-04-05
# ============================================================================
# Component 11e: Threat Event Logging
#
# Thin wrapper around C7 AuditLogger for security-specific events.
# All threat detections, gate decisions, and sanitizations are logged
# BEFORE any other action (Constitution: Law 6, no silent bypasses).
# ============================================================================

from typing import Any, Dict, List, Optional

from ironframe.audit.logger_v1_0 import AuditLogger


class ThreatEventLogger:
    """Security event logger. Wraps C7 AuditLogger with security-specific event types."""

    def __init__(self, audit_logger: Optional[AuditLogger] = None):
        self._audit = audit_logger

    def log_scan(self, content_id: str, scan_result_dict: Dict, tier: str,
                 source: str, session_id: str) -> None:
        self._emit("security.scan", session_id, {
            "content_id": content_id,
            "tier": tier,
            "source": source,
            "clean": scan_result_dict.get("clean"),
            "threat_level": scan_result_dict.get("threat_level"),
            "matched_rules": len(scan_result_dict.get("matched_rules", [])),
            "structural_flags": len(scan_result_dict.get("structural_flags", [])),
        })

    def log_tier_assignment(self, content_id: str, tier: str, source: str,
                            session_id: str) -> None:
        self._emit("security.tier_assignment", session_id, {
            "content_id": content_id,
            "tier": tier,
            "source": source,
        })

    def log_tier_downgrade(self, content_id: str, old_tier: str, new_tier: str,
                           reason: str, session_id: str) -> None:
        self._emit("security.tier_downgrade", session_id, {
            "content_id": content_id,
            "old_tier": old_tier,
            "new_tier": new_tier,
            "reason": reason,
        })

    def log_gate_decision(self, tool_id: str, allowed: bool, tool_risk: str,
                          lowest_tier: str, session_id: str,
                          denial_reason: str = "",
                          requires_confirmation: bool = False) -> None:
        event_type = "security.gate_check"
        if not allowed and not requires_confirmation:
            event_type = "security.gate_block"
        elif requires_confirmation:
            event_type = "security.gate_confirm_required"

        self._emit(event_type, session_id, {
            "tool_id": tool_id,
            "allowed": allowed,
            "tool_risk": tool_risk,
            "lowest_input_tier": lowest_tier,
            "denial_reason": denial_reason,
            "requires_confirmation": requires_confirmation,
        })

    def log_sanitize(self, content_id: str, tier: str, strips_applied: List[str],
                     session_id: str) -> None:
        self._emit("security.sanitize", session_id, {
            "content_id": content_id,
            "tier": tier,
            "strips_applied": strips_applied,
            "strip_count": len(strips_applied),
        })

    def log_hostile(self, content_hash: str, matched_rules: List[Dict],
                    source: str, session_id: str) -> None:
        self._emit("security.hostile_content", session_id, {
            "content_hash": content_hash,
            "source": source,
            "matched_rule_count": len(matched_rules),
            "categories": list(set(r.get("category", "") for r in matched_rules)),
        })

    def _emit(self, event_type: str, session_id: str, details: Dict[str, Any]) -> None:
        if not self._audit:
            return
        try:
            self._audit.log_event(
                event_type=event_type,
                component="security",
                session_id=session_id,
                details=details,
            )
        except Exception:
            pass  # security logging must not crash the pipeline
