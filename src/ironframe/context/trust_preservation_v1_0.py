# ============================================================================
# ironframe/context/trust_preservation_v1_0.py - v1.0
# Last updated: 2026-04-06
# ============================================================================
# Component 9d: Trust Metadata Preservation Invariant
#
# HARD INVARIANT: content that enters C9 with a trust tier must exit
# with that tier intact, regardless of compression.
#
# - SYSTEM-tier instructions in summaries retain SYSTEM designation
# - EXTERNAL-tier content from C11 retains tier + sanitization flags
# - Violations are tracked in telemetry (should always be zero)
# ============================================================================

from typing import Dict, List

from ironframe.context.zones_v1_0 import ContentChunk, ZoneContent


def verify_preservation(
    input_chunks: List[ContentChunk],
    output_chunks: List[ContentChunk],
) -> List[str]:
    """Verify that trust tiers survived compression.

    Checks that every chunk_id present in output has the same trust_tier
    as it had in input. Returns list of violations (empty = preserved).
    """
    input_tiers: Dict[str, int] = {c.chunk_id: c.trust_tier for c in input_chunks}
    violations = []

    for chunk in output_chunks:
        if chunk.chunk_id in input_tiers:
            expected = input_tiers[chunk.chunk_id]
            if chunk.trust_tier != expected:
                violations.append(
                    f"Chunk '{chunk.chunk_id}' trust tier changed: "
                    f"{expected} -> {chunk.trust_tier}"
                )

    return violations


def verify_package_preservation(
    input_zones: Dict[str, ZoneContent],
    output_zones: Dict[str, ZoneContent],
) -> List[str]:
    """Verify trust preservation across an entire context package.

    Collects all chunks from input and output, checks each surviving chunk.
    """
    input_chunks = []
    output_chunks = []
    for zone in input_zones.values():
        input_chunks.extend(zone.chunks)
    for zone in output_zones.values():
        output_chunks.extend(zone.chunks)

    return verify_preservation(input_chunks, output_chunks)


def highest_system_tier_in_zone(zone: ZoneContent) -> bool:
    """Check if a zone contains any SYSTEM-tier content (tier 4).

    Used to verify protection zones are intact.
    """
    return any(c.trust_tier >= 4 for c in zone.chunks)
