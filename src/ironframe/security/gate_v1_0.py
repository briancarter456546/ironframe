# ============================================================================
# ironframe/security/gate_v1_0.py - v1.0
# Last updated: 2026-04-05
# ============================================================================
# Component 11c: Action Gate — Provenance-Based Structural Barrier
#
# NOT a content filter. A pre-execution structural barrier that checks
# input provenance: what inputs fed the model call that produced this
# action request, and what were their trust tiers?
#
# If the input chain contains ANY EXTERNAL-tier content that contributed
# to a HIGH/CRITICAL action, the gate requires secondary confirmation.
# HOSTILE-flagged inputs block ALL downstream actions.
#
# The model cannot reason past this gate.
#
# Constitution: Law 3 (agents untrusted), RTM IF-REQ-008
# ============================================================================

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ironframe.security.trust_v1_0 import TrustTier, TrustedContent
from ironframe.tool_governance.registry_v1_0 import ToolRegistry, ToolRisk


# Gate decision constants
ALLOW = "allow"
CONFIRM = "confirm"
BLOCK = "block"


@dataclass
class ProvenanceChain:
    """The set of inputs that contributed to an action request.

    Built from a list of TrustedContent IDs. Computes the worst
    (lowest) trust tier in the chain and flags for external/hostile.
    """
    chain_id: str
    input_content_ids: List[str]
    input_tiers: List[int]        # TrustTier values for each input
    lowest_tier: int              # min(input_tiers) — worst trust level
    has_external: bool            # any tier <= EXTERNAL
    has_hostile: bool             # any tier == HOSTILE
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    @property
    def lowest_tier_name(self) -> str:
        return TrustTier(self.lowest_tier).name if self.input_tiers else "UNKNOWN"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "input_count": len(self.input_content_ids),
            "lowest_tier": self.lowest_tier_name,
            "has_external": self.has_external,
            "has_hostile": self.has_hostile,
        }


@dataclass
class GateDecision:
    """Result of the action gate check."""
    allowed: bool
    action: str                    # "allow", "confirm", "block"
    tool_id: str
    tool_risk: str                 # from C12 ToolRegistry (never duplicated)
    provenance_chain_id: str
    lowest_input_tier: str
    denial_reason: str = ""
    requires_confirmation: bool = False
    confirmation_prompt: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "allowed": self.allowed,
            "action": self.action,
            "tool_id": self.tool_id,
            "tool_risk": self.tool_risk,
            "lowest_input_tier": self.lowest_input_tier,
            "provenance_chain_id": self.provenance_chain_id,
        }
        if not self.allowed:
            d["denial_reason"] = self.denial_reason
            d["requires_confirmation"] = self.requires_confirmation
        if self.confirmation_prompt:
            d["confirmation_prompt"] = self.confirmation_prompt
        return d


def build_provenance_chain(
    input_content_ids: List[str],
    content_store: Dict[str, TrustedContent],
) -> ProvenanceChain:
    """Build a ProvenanceChain from stored content IDs.

    Flat lookup + min(tiers). Also traverses parent_content_ids to capture
    full ancestry. No graph database — just recursive ID collection.
    """
    all_tiers = []
    visited = set()

    def _collect(content_id: str) -> None:
        if content_id in visited:
            return
        visited.add(content_id)
        content = content_store.get(content_id)
        if content:
            all_tiers.append(content.trust_tier)
            for parent_id in content.parent_content_ids:
                _collect(parent_id)

    for cid in input_content_ids:
        _collect(cid)

    lowest = min(all_tiers) if all_tiers else TrustTier.EXTERNAL.value
    has_external = any(t <= TrustTier.EXTERNAL for t in all_tiers)
    has_hostile = any(t == TrustTier.HOSTILE for t in all_tiers)

    return ProvenanceChain(
        chain_id=str(uuid.uuid4())[:12],
        input_content_ids=list(visited),
        input_tiers=all_tiers,
        lowest_tier=lowest,
        has_external=has_external,
        has_hostile=has_hostile,
    )


# ============================================================================
# DECISION MATRIX
#
# | Lowest Tier  | LOW    | MEDIUM | HIGH    | CRITICAL |
# |--------------|--------|--------|---------|----------|
# | SYSTEM       | ALLOW  | ALLOW  | ALLOW   | ALLOW    |
# | OPERATOR     | ALLOW  | ALLOW  | ALLOW   | ALLOW    |
# | USER         | ALLOW  | ALLOW  | ALLOW   | CONFIRM  |
# | EXTERNAL     | ALLOW  | ALLOW  | CONFIRM | BLOCK    |
# | HOSTILE      | BLOCK  | BLOCK  | BLOCK   | BLOCK    |
# ============================================================================

_RISK_ORDER = {
    ToolRisk.LOW.value: 0,
    ToolRisk.MEDIUM.value: 1,
    ToolRisk.HIGH.value: 2,
    ToolRisk.CRITICAL.value: 3,
}


def _decide(lowest_tier: int, tool_risk_str: str) -> str:
    """Pure decision function: returns ALLOW, CONFIRM, or BLOCK."""
    risk_level = _RISK_ORDER.get(tool_risk_str, 1)

    # HOSTILE blocks everything
    if lowest_tier <= TrustTier.HOSTILE:
        return BLOCK

    # EXTERNAL
    if lowest_tier == TrustTier.EXTERNAL:
        if risk_level >= 3:  # CRITICAL
            return BLOCK
        if risk_level >= 2:  # HIGH
            return CONFIRM
        return ALLOW

    # USER
    if lowest_tier == TrustTier.USER:
        if risk_level >= 3:  # CRITICAL
            return CONFIRM
        return ALLOW

    # OPERATOR or SYSTEM
    return ALLOW


class ActionGate:
    """Pre-execution structural barrier based on input provenance.

    Reads tool risk from C12's ToolRegistry — never duplicates risk data.
    Checks the trust tiers of all inputs that fed the action request.
    """

    def __init__(self, tool_registry: ToolRegistry, threat_logger=None):
        self._tool_registry = tool_registry
        self._threat_log = threat_logger

    def check(
        self,
        tool_id: str,
        provenance: ProvenanceChain,
        session_id: str = "",
    ) -> GateDecision:
        """Check whether an action is allowed given its input provenance.

        This is the structural barrier. The model cannot reason past it.
        """
        # Get tool risk from C12 registry (no duplication)
        tool = self._tool_registry.get(tool_id)
        if not tool:
            decision = GateDecision(
                allowed=False,
                action=BLOCK,
                tool_id=tool_id,
                tool_risk="UNKNOWN",
                provenance_chain_id=provenance.chain_id,
                lowest_input_tier=provenance.lowest_tier_name,
                denial_reason="Tool not registered in C12 registry",
            )
            self._log_decision(decision, session_id)
            return decision

        tool_risk = tool.risk
        action = _decide(provenance.lowest_tier, tool_risk)

        if action == ALLOW:
            decision = GateDecision(
                allowed=True,
                action=ALLOW,
                tool_id=tool_id,
                tool_risk=tool_risk,
                provenance_chain_id=provenance.chain_id,
                lowest_input_tier=provenance.lowest_tier_name,
            )
        elif action == CONFIRM:
            decision = GateDecision(
                allowed=False,
                action=CONFIRM,
                tool_id=tool_id,
                tool_risk=tool_risk,
                provenance_chain_id=provenance.chain_id,
                lowest_input_tier=provenance.lowest_tier_name,
                requires_confirmation=True,
                denial_reason=f"Input chain contains {provenance.lowest_tier_name}-tier content; "
                              f"{tool_risk} tool requires confirmation",
                confirmation_prompt=f"Action '{tool_id}' (risk: {tool_risk}) was triggered by "
                                    f"content with trust tier {provenance.lowest_tier_name}. "
                                    f"Confirm this action?",
            )
        else:  # BLOCK
            reason = "HOSTILE content in input chain blocks all actions" if provenance.has_hostile else \
                     f"Input chain contains {provenance.lowest_tier_name}-tier content; " \
                     f"{tool_risk} tool is blocked at this trust level"
            decision = GateDecision(
                allowed=False,
                action=BLOCK,
                tool_id=tool_id,
                tool_risk=tool_risk,
                provenance_chain_id=provenance.chain_id,
                lowest_input_tier=provenance.lowest_tier_name,
                denial_reason=reason,
            )

        self._log_decision(decision, session_id)
        return decision

    def _log_decision(self, decision: GateDecision, session_id: str) -> None:
        if self._threat_log:
            self._threat_log.log_gate_decision(
                tool_id=decision.tool_id,
                allowed=decision.allowed,
                tool_risk=decision.tool_risk,
                lowest_tier=decision.lowest_input_tier,
                session_id=session_id,
                denial_reason=decision.denial_reason,
                requires_confirmation=decision.requires_confirmation,
            )
