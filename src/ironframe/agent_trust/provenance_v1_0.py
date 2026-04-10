# ============================================================================
# ironframe/agent_trust/provenance_v1_0.py - v1.0
# Last updated: 2026-04-07
# ============================================================================
# Component 17f: Output Provenance Tagging
#
# Every agent output is tagged with trust context before leaving.
# Downstream components use the tag to calibrate trust. A T2 output
# with anomaly events != a clean T3 output.
#
# Tags cannot be stripped or modified by agents.
# ============================================================================

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


@dataclass
class OutputProvenance:
    """Trust context tag attached to every agent output.

    Immutable once created. Agents cannot strip or modify this.
    """
    agent_id: str
    agent_type: str
    autonomy_tier: int
    session_id: str
    kb_entities_consulted: List[str] = field(default_factory=list)
    tool_calls_made: List[str] = field(default_factory=list)
    anomaly_score: float = 0.0
    tier_downgrades: List[str] = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    @property
    def has_anomalies(self) -> bool:
        return self.anomaly_score > 0.0 or len(self.tier_downgrades) > 0

    @property
    def trust_summary(self) -> str:
        """One-line trust summary for downstream consumers."""
        flags = []
        if self.has_anomalies:
            flags.append(f"anomaly={self.anomaly_score:.2f}")
        if self.tier_downgrades:
            flags.append(f"downgrades={len(self.tier_downgrades)}")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        return f"T{self.autonomy_tier}/{self.agent_type}{flag_str}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "autonomy_tier": self.autonomy_tier,
            "session_id": self.session_id,
            "kb_entities_consulted": self.kb_entities_consulted,
            "tool_calls_made": self.tool_calls_made,
            "anomaly_score": round(self.anomaly_score, 4),
            "tier_downgrades": self.tier_downgrades,
            "has_anomalies": self.has_anomalies,
            "trust_summary": self.trust_summary,
            "timestamp": self.timestamp,
        }


def create_provenance(
    session_id: str,
    agent_type: str,
    autonomy_tier: int,
    agent_id: str = "",
    kb_entities: List[str] = None,
    tool_calls: List[str] = None,
    anomaly_score: float = 0.0,
    tier_downgrades: List[str] = None,
) -> OutputProvenance:
    """Factory for output provenance tags."""
    return OutputProvenance(
        agent_id=agent_id or session_id,
        agent_type=agent_type,
        autonomy_tier=autonomy_tier,
        session_id=session_id,
        kb_entities_consulted=kb_entities or [],
        tool_calls_made=tool_calls or [],
        anomaly_score=anomaly_score,
        tier_downgrades=tier_downgrades or [],
    )
