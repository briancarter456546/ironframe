# ============================================================================
# ironframe/security/trust_v1_0.py - v1.0
# Last updated: 2026-04-05
# ============================================================================
# Component 11a: Input Trust Tiering
#
# Every input to the system is assigned a trust tier BEFORE it reaches
# the model. The tier travels with the content as metadata — it cannot
# be stripped or upgraded by model reasoning.
#
# Constitution: Law 3 (agents untrusted by default)
# ============================================================================

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Dict, List, Optional


class TrustTier(IntEnum):
    """Trust tiers ordered by privilege. Higher = more trusted.

    IntEnum so min() over a list of tiers returns the least trusted.
    """
    HOSTILE = 0      # confirmed malicious or failed detection
    EXTERNAL = 1     # tool outputs, retrieved docs, agent messages
    USER = 2         # human user input
    OPERATOR = 3     # deployment config, human-reviewed
    SYSTEM = 4       # constitution, contracts, hardcoded prompts


# Source -> default trust tier mapping
_SOURCE_TIER_MAP = {
    "system": TrustTier.SYSTEM,
    "system_prompt": TrustTier.SYSTEM,
    "constitution": TrustTier.SYSTEM,
    "operator_config": TrustTier.OPERATOR,
    "session_init": TrustTier.OPERATOR,
    "skill_contract": TrustTier.OPERATOR,
    "user_input": TrustTier.USER,
    "user_message": TrustTier.USER,
    "tool_output": TrustTier.EXTERNAL,
    "retrieved_doc": TrustTier.EXTERNAL,
    "web_search": TrustTier.EXTERNAL,
    "web_content": TrustTier.EXTERNAL,
    "agent_message": TrustTier.EXTERNAL,  # C17 stub: default EXTERNAL
    "external": TrustTier.EXTERNAL,
    "unknown": TrustTier.EXTERNAL,        # unknown = treat as external
}


@dataclass
class TrustedContent:
    """Content tagged with trust tier and provenance metadata.

    Once created, the trust tier can only be DOWNGRADED (e.g., to HOSTILE
    after injection detection), never upgraded by model reasoning.
    """
    content_id: str
    trust_tier: int              # TrustTier value
    source: str                  # "user_input", "tool_output", etc.
    content_hash: str            # SHA-256 of raw content
    content_length: int
    raw_content: str             # original text
    sanitized_content: str       # post-sanitization (same as raw if no sanitization)
    detection_results: List[Dict[str, Any]] = field(default_factory=list)
    parent_content_ids: List[str] = field(default_factory=list)  # provenance chain
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    @property
    def tier_name(self) -> str:
        return TrustTier(self.trust_tier).name

    @property
    def is_hostile(self) -> bool:
        return self.trust_tier == TrustTier.HOSTILE

    @property
    def is_external(self) -> bool:
        return self.trust_tier <= TrustTier.EXTERNAL

    def downgrade_to(self, new_tier: int) -> None:
        """Downgrade trust tier. Cannot upgrade — only downgrade allowed."""
        if new_tier < self.trust_tier:
            self.trust_tier = new_tier

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content_id": self.content_id,
            "trust_tier": self.tier_name,
            "source": self.source,
            "content_hash": self.content_hash,
            "content_length": self.content_length,
            "parent_content_ids": self.parent_content_ids,
            "timestamp": self.timestamp,
        }


def classify_trust_tier(source: str) -> TrustTier:
    """Classify a content source into a trust tier.

    Unknown sources default to EXTERNAL (conservative).
    """
    return _SOURCE_TIER_MAP.get(source, TrustTier.EXTERNAL)


def create_trusted_content(
    content: str,
    source: str,
    parent_ids: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> TrustedContent:
    """Factory for TrustedContent with auto-generated ID, hash, and tier."""
    tier = classify_trust_tier(source)
    return TrustedContent(
        content_id=str(uuid.uuid4())[:12],
        trust_tier=tier.value,
        source=source,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        content_length=len(content),
        raw_content=content,
        sanitized_content=content,  # updated by sanitizer
        parent_content_ids=parent_ids or [],
        metadata=metadata or {},
    )


def attest_agent_tier(agent_id: str) -> TrustTier:
    """C17 stub: check if an agent has earned a higher trust tier.

    v1: always returns EXTERNAL. When Component 17 is built, this
    will delegate to the agent trust attestation system.
    """
    return TrustTier.EXTERNAL
