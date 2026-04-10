# ============================================================================
# ironframe/context/zones_v1_0.py - v1.0
# Last updated: 2026-04-06
# ============================================================================
# Component 9a: Zone Architecture
#
# Fixed zone sequence. NEVER reordered. This IS the stable prefix that
# enables prompt cache hits.
#
# Three PROTECTION zones: CONSTITUTIONAL, CONTRACT, TOOL_DEFINITIONS
#   -> NEVER compressed, NEVER reordered, NEVER pruned
#
# Two MANAGED zones: RETRIEVED_CONTEXT, CONVERSATION_HISTORY
#   -> Compression allowed, managed by budget
#   -> Overflow precedence: CONVERSATION_HISTORY first, then RETRIEVED_CONTEXT
#
# One TERMINAL zone: CURRENT_TASK
#   -> Always last, never compressed, floor protected
# ============================================================================

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Dict, List, Optional


class ContextZone(str, Enum):
    """Context zones in fixed sequence order."""
    CONSTITUTIONAL = "constitutional"
    CONTRACT = "contract"
    TOOL_DEFINITIONS = "tool_definitions"
    RETRIEVED_CONTEXT = "retrieved_context"
    CONVERSATION_HISTORY = "conversation_history"
    CURRENT_TASK = "current_task"


# Fixed sequence — index IS position. NEVER reordered.
ZONE_SEQUENCE = [
    ContextZone.CONSTITUTIONAL,
    ContextZone.CONTRACT,
    ContextZone.TOOL_DEFINITIONS,
    ContextZone.RETRIEVED_CONTEXT,
    ContextZone.CONVERSATION_HISTORY,
    ContextZone.CURRENT_TASK,
]

# Protection zones — NEVER compressed, NEVER pruned
PROTECTED_ZONES = frozenset({
    ContextZone.CONSTITUTIONAL,
    ContextZone.CONTRACT,
    ContextZone.TOOL_DEFINITIONS,
})

# Managed zones — compression allowed
MANAGED_ZONES = frozenset({
    ContextZone.RETRIEVED_CONTEXT,
    ContextZone.CONVERSATION_HISTORY,
})

# Compression precedence: compress in this order (addition #2)
COMPRESSION_PRECEDENCE = [
    ContextZone.CONVERSATION_HISTORY,  # compress first
    ContextZone.RETRIEVED_CONTEXT,     # compress second
]

# Default trust tiers per zone (from C11 TrustTier values)
ZONE_DEFAULT_TRUST = {
    ContextZone.CONSTITUTIONAL: 4,       # SYSTEM
    ContextZone.CONTRACT: 4,             # SYSTEM
    ContextZone.TOOL_DEFINITIONS: 4,     # SYSTEM
    ContextZone.RETRIEVED_CONTEXT: 3,    # OPERATOR
    ContextZone.CONVERSATION_HISTORY: 2, # USER
    ContextZone.CURRENT_TASK: 2,         # USER (varies)
}


@dataclass
class ContentChunk:
    """A single piece of content within a zone."""
    chunk_id: str
    text: str
    token_count: int
    trust_tier: int           # from C11 TrustTier
    source_id: str = ""       # provenance content_id from C11
    relevance_score: float = 1.0
    timestamp: str = ""
    compressed: bool = False
    compression_passes: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ZoneContent:
    """Contents of a single zone in the context package."""
    zone: str                 # ContextZone value
    position: int             # fixed position in sequence
    chunks: List[ContentChunk] = field(default_factory=list)
    compressed: bool = False

    @property
    def token_count(self) -> int:
        return sum(c.token_count for c in self.chunks)

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    @property
    def is_protected(self) -> bool:
        return self.zone in {z.value for z in PROTECTED_ZONES}

    @property
    def is_managed(self) -> bool:
        return self.zone in {z.value for z in MANAGED_ZONES}

    @property
    def lowest_trust_tier(self) -> int:
        if not self.chunks:
            return ZONE_DEFAULT_TRUST.get(ContextZone(self.zone), 2)
        return min(c.trust_tier for c in self.chunks)

    def add_chunk(self, chunk: ContentChunk) -> None:
        self.chunks.append(chunk)

    def assembled_text(self) -> str:
        """Concatenate all chunks in order."""
        return "\n".join(c.text for c in self.chunks if c.text)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "zone_type": self.zone,
            "position": self.position,
            "token_count": self.token_count,
            "trust_tier": self.lowest_trust_tier,
            "compressed": self.compressed,
            "chunks": self.chunk_count,
        }


def create_empty_package() -> Dict[str, ZoneContent]:
    """Create an empty context package with all zones in fixed order."""
    package = {}
    for i, zone in enumerate(ZONE_SEQUENCE):
        package[zone.value] = ZoneContent(zone=zone.value, position=i)
    return package


def estimate_tokens(text: str) -> int:
    """Rough token estimation. 1 token ~= 4 characters for English text."""
    return max(1, len(text) // 4)
