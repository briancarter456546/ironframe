# ============================================================================
# ironframe/agent_trust/tiers_v1_0.py - v1.0
# Last updated: 2026-04-07
# ============================================================================
# Component 17b: Autonomy Tiers with Blast Radius
#
# Four tiers with explicit permission boundaries. Enforcement via C4/C12,
# not model reasoning. Tier assignments come ONLY from verified SessionTokens.
#
# Clarification: agents cannot self-declare tiers. Any attempt to claim a
# higher tier than the token grants is ignored and logged as anomaly.
# ============================================================================

from enum import IntEnum
from typing import Any, Dict, List


class AutonomyTier(IntEnum):
    """Autonomy tiers ordered by privilege. Higher = more trusted."""
    OBSERVE = 1      # read-only, no writes, no tool calls
    LIMITED = 2      # reads + writes to analytical/ephemeral, no external tools
    STANDARD = 3     # full access within policy, governed tasks need completion gate
    ELEVATED = 4     # human-approved elevated operations, time-boxed


# Blast radius definitions per tier
TIER_PERMISSIONS: Dict[int, Dict[str, Any]] = {
    AutonomyTier.OBSERVE: {
        "read_kb": True,
        "write_kb": False,
        "write_kb_classes": [],
        "tool_calls": False,
        "external_tools": False,
        "canonical_write": False,
        "requires_completion_gate": False,
        "time_boxed": False,
        "description": "Observe only. No writes. No tool calls.",
    },
    AutonomyTier.LIMITED: {
        "read_kb": True,
        "write_kb": True,
        "write_kb_classes": ["analytical", "ephemeral"],
        "tool_calls": True,
        "external_tools": False,
        "canonical_write": False,
        "requires_completion_gate": False,
        "time_boxed": False,
        "description": "Reads + writes to Analytical/Ephemeral. No Canonical. No external tools.",
    },
    AutonomyTier.STANDARD: {
        "read_kb": True,
        "write_kb": True,
        "write_kb_classes": ["analytical", "ephemeral", "authoritative_domain"],
        "tool_calls": True,
        "external_tools": True,
        "canonical_write": False,
        "requires_completion_gate": True,
        "time_boxed": False,
        "description": "Full access within policy. Governed tasks require completion gate.",
    },
    AutonomyTier.ELEVATED: {
        "read_kb": True,
        "write_kb": True,
        "write_kb_classes": ["analytical", "ephemeral", "authoritative_domain", "canonical"],
        "tool_calls": True,
        "external_tools": True,
        "canonical_write": True,
        "requires_completion_gate": True,
        "time_boxed": True,
        "description": "Human-approved elevated operations. Time-boxed. Not the default.",
    },
}


def get_tier_permissions(tier: int) -> Dict[str, Any]:
    """Get permission set for a tier. Unknown tiers default to OBSERVE."""
    return TIER_PERMISSIONS.get(tier, TIER_PERMISSIONS[AutonomyTier.OBSERVE])


def tier_name(tier: int) -> str:
    """Human-readable tier name."""
    try:
        return AutonomyTier(tier).name
    except ValueError:
        return f"UNKNOWN({tier})"


def is_action_allowed(tier: int, action: str, target_class: str = "") -> bool:
    """Check if a specific action is allowed at this tier.

    Used by permissions_v1_0.py as the single authority for permission decisions.
    """
    perms = get_tier_permissions(tier)

    if action == "read_kb":
        return perms["read_kb"]

    if action == "write_kb":
        if not perms["write_kb"]:
            return False
        if target_class and target_class not in perms["write_kb_classes"]:
            return False
        return True

    if action == "canonical_write":
        return perms["canonical_write"]

    if action == "tool_call":
        return perms["tool_calls"]

    if action == "external_tool":
        return perms["external_tools"]

    # Unknown action = deny
    return False
