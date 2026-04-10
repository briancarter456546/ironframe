# ============================================================================
# ironframe/context/rot_detector_v1_0.py - v1.0
# Last updated: 2026-04-06
# ============================================================================
# Component 9e: Context Rot Detection
#
# Context rot = important info pushed to mid-window positions where
# attention is weakest ("lost in the middle" effect).
#
# If CURRENT_TASK starts beyond 75% of window: context_rot_risk event.
# If can't get below 75% after mitigation: escalate, don't proceed.
# ============================================================================

from dataclasses import dataclass
from typing import Any, Dict, List

from ironframe.context.zones_v1_0 import ContextZone, ZoneContent, ZONE_SEQUENCE


ROT_THRESHOLD = 0.75  # CURRENT_TASK must start before 75% of window


@dataclass
class RotAssessment:
    """Result of context rot detection."""
    current_task_start_pct: float   # where CURRENT_TASK begins (0.0-1.0)
    at_risk: bool                   # True if above ROT_THRESHOLD
    total_tokens: int
    tokens_before_task: int
    risk_score: float               # 0.0 (no risk) to 1.0 (critical)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_task_start_pct": round(self.current_task_start_pct, 4),
            "at_risk": self.at_risk,
            "total_tokens": self.total_tokens,
            "tokens_before_task": self.tokens_before_task,
            "risk_score": round(self.risk_score, 4),
        }


def assess_rot(zones: Dict[str, ZoneContent], total_budget: int) -> RotAssessment:
    """Assess context rot risk from assembled zones.

    Measures what % of total budget is consumed before CURRENT_TASK starts.
    """
    tokens_before_task = 0
    total_tokens = 0

    for zone_enum in ZONE_SEQUENCE:
        zone = zones.get(zone_enum.value)
        if not zone:
            continue
        if zone_enum == ContextZone.CURRENT_TASK:
            total_tokens += zone.token_count
            break
        tokens_before_task += zone.token_count
        total_tokens += zone.token_count

    # Add CURRENT_TASK tokens to total
    task_zone = zones.get(ContextZone.CURRENT_TASK.value)
    if task_zone:
        total_tokens += task_zone.token_count

    effective_total = max(total_budget, total_tokens, 1)
    start_pct = tokens_before_task / effective_total

    # Risk score: 0 at 50%, 0.5 at 75%, 1.0 at 100%
    if start_pct <= 0.50:
        risk_score = 0.0
    elif start_pct <= ROT_THRESHOLD:
        risk_score = (start_pct - 0.50) / 0.50  # 0 to 1 between 50%-75%
    else:
        risk_score = min(1.0, 0.5 + (start_pct - ROT_THRESHOLD) * 2.0)

    return RotAssessment(
        current_task_start_pct=start_pct,
        at_risk=start_pct > ROT_THRESHOLD,
        total_tokens=total_tokens,
        tokens_before_task=tokens_before_task,
        risk_score=risk_score,
    )
