# ============================================================================
# ironframe/kb/freshness_v1_0.py - v1.0
# Last updated: 2026-04-06
# ============================================================================
# Component 10e: Freshness Management
#
# Every KB entity has last_verified_at and freshness policy per source class.
# Stale content is retrieved but flagged — stale is better than nothing.
# Freshness signals forwarded to C18 (Drift Engine) when built.
# ============================================================================

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional


# Stale thresholds by source class
_FRESHNESS_THRESHOLDS = {
    "canonical": None,                # change-driven, no fixed threshold
    "authoritative_domain": 90,       # days
    "analytical": 30,                 # days
    "ephemeral": 0,                   # session-scoped, auto-expire
}

# Actions on stale content
_STALE_ACTIONS = {
    "canonical": "block_conformance",
    "authoritative_domain": "confidence_penalty",
    "analytical": "mark_non_authoritative",
    "ephemeral": "auto_expire",
}


@dataclass
class FreshnessCheck:
    """Result of checking freshness of a KB entity."""
    entity_id: str
    source_class: str
    last_verified_at: str
    freshness_status: str      # fresh, stale, unknown, expired
    stale_action: str          # what to do about it
    days_since_verified: int
    threshold_days: Optional[int]

    @property
    def is_stale(self) -> bool:
        return self.freshness_status in ("stale", "expired")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "source_class": self.source_class,
            "freshness_status": self.freshness_status,
            "stale_action": self.stale_action,
            "days_since_verified": self.days_since_verified,
        }


def check_freshness(
    entity_id: str,
    source_class: str,
    last_verified_at: str,
) -> FreshnessCheck:
    """Check freshness of a single entity based on its source class policy."""
    threshold = _FRESHNESS_THRESHOLDS.get(source_class)
    action = _STALE_ACTIONS.get(source_class, "")

    # Parse last_verified_at
    days_since = -1
    if last_verified_at:
        try:
            verified_dt = datetime.fromisoformat(last_verified_at)
            if verified_dt.tzinfo is None:
                verified_dt = verified_dt.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - verified_dt
            days_since = delta.days
        except (ValueError, TypeError):
            pass

    # Determine status
    if source_class == "ephemeral":
        status = "expired" if days_since > 0 else "fresh"
    elif threshold is None:
        # Canonical: change-driven, no fixed threshold
        status = "fresh" if days_since >= 0 else "unknown"
    elif days_since < 0:
        status = "unknown"
    elif days_since > threshold:
        status = "stale"
    else:
        status = "fresh"

    return FreshnessCheck(
        entity_id=entity_id,
        source_class=source_class,
        last_verified_at=last_verified_at,
        freshness_status=status,
        stale_action=action if status in ("stale", "expired") else "",
        days_since_verified=max(0, days_since),
        threshold_days=threshold,
    )


def update_verified_timestamp(store, chunk_id: str) -> None:
    """Mark a chunk as freshly verified."""
    now = datetime.now(timezone.utc).isoformat()
    conn = store._get_conn()
    conn.execute(
        "UPDATE kb_chunks SET last_verified_at = ?, freshness_status = 'fresh' WHERE chunk_id = ?",
        (now, chunk_id),
    )
    conn.commit()


def expire_ephemeral(store, session_id: str = "") -> int:
    """Expire all ephemeral chunks. Returns count expired."""
    conn = store._get_conn()
    result = conn.execute(
        "UPDATE kb_chunks SET status = 'expired' WHERE source_class = 'ephemeral' AND status = 'active'"
    )
    conn.commit()
    return result.rowcount
