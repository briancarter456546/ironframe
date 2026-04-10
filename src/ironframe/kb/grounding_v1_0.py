# ============================================================================
# ironframe/kb/grounding_v1_0.py - v1.0
# Last updated: 2026-04-06
# ============================================================================
# Component 10c: Grounding Attachment
#
# Converts retrieval results into trust-tiered GroundedChunks compatible
# with C9's RETRIEVED_CONTEXT zone. Each chunk carries provenance:
# source class, freshness status, relevance score, source document ID.
# ============================================================================

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class SourceClass(str, Enum):
    CANONICAL = "canonical"
    AUTHORITATIVE_DOMAIN = "authoritative_domain"
    ANALYTICAL = "analytical"
    EPHEMERAL = "ephemeral"


# Source class -> default trust tier (from C11 TrustTier values)
_SOURCE_CLASS_TRUST = {
    SourceClass.CANONICAL: 4,             # SYSTEM
    SourceClass.AUTHORITATIVE_DOMAIN: 3,  # OPERATOR
    SourceClass.ANALYTICAL: 2,            # USER
    SourceClass.EPHEMERAL: 2,             # USER
}

# Confidence penalties for stale content
_STALE_CONFIDENCE_PENALTY = {
    "canonical": 0.0,              # canonical staleness blocks at C18, not here
    "authoritative_domain": 0.2,   # 20% penalty
    "analytical": 0.3,             # 30% penalty
    "ephemeral": 1.0,              # fully penalized (expired)
}


@dataclass
class GroundedChunk:
    """A trust-tiered chunk ready for C9's RETRIEVED_CONTEXT zone.

    Carries full provenance: source class, freshness, relevance, origin.
    """
    chunk_id: str
    content: str
    source_class: str
    entity_type: str
    trust_tier: int
    relevance_score: float
    freshness_status: str       # fresh, stale, unknown, expired
    freshness_flag: bool        # True if stale
    source_document_id: str
    retrieved_at: str
    confidence_penalty: float = 0.0

    def to_c9_dict(self) -> Dict[str, Any]:
        """Format for C9 RETRIEVED_CONTEXT zone interface."""
        return {
            "text": self.content,
            "trust_tier": self.trust_tier,
            "source_id": self.chunk_id,
            "freshness_flag": self.freshness_flag,
            "source_class": self.source_class,
            "relevance_score": self.relevance_score,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "source_class": self.source_class,
            "entity_type": self.entity_type,
            "trust_tier": self.trust_tier,
            "relevance_score": round(self.relevance_score, 4),
            "freshness_status": self.freshness_status,
            "freshness_flag": self.freshness_flag,
            "confidence_penalty": self.confidence_penalty,
            "source_document_id": self.source_document_id,
            "retrieved_at": self.retrieved_at,
            "content_length": len(self.content),
        }


def ground_chunks(retrieval_chunks: List[Dict[str, Any]]) -> List[GroundedChunk]:
    """Convert raw retrieval results into trust-tiered GroundedChunks.

    Assigns trust tier from source class, applies freshness penalties.
    """
    now = datetime.now(timezone.utc).isoformat()
    grounded = []

    for chunk in retrieval_chunks:
        source_class = chunk.get("source_class", "analytical")
        sc_enum = SourceClass(source_class) if source_class in [s.value for s in SourceClass] else SourceClass.ANALYTICAL
        trust_tier = _SOURCE_CLASS_TRUST.get(sc_enum, 2)

        freshness_flag = chunk.get("freshness_flag", False)
        freshness_status = chunk.get("freshness_status", "unknown")
        penalty = _STALE_CONFIDENCE_PENALTY.get(source_class, 0.0) if freshness_flag else 0.0

        grounded.append(GroundedChunk(
            chunk_id=chunk.get("chunk_id", str(uuid.uuid4())[:12]),
            content=chunk.get("content", ""),
            source_class=source_class,
            entity_type=chunk.get("entity_type", ""),
            trust_tier=trust_tier,
            relevance_score=chunk.get("relevance_score", 0.0),
            freshness_status=freshness_status,
            freshness_flag=freshness_flag,
            source_document_id=chunk.get("source_document_id", ""),
            retrieved_at=now,
            confidence_penalty=penalty,
        ))

    return grounded


def ground_entities(retrieval_entities: List[Dict[str, Any]]) -> List[GroundedChunk]:
    """Convert graph traversal entity results into GroundedChunks.

    Entity properties are serialized as content text.
    """
    now = datetime.now(timezone.utc).isoformat()
    grounded = []

    for entity in retrieval_entities:
        source_class = entity.get("source_class", "authoritative_domain")
        sc_enum = SourceClass(source_class) if source_class in [s.value for s in SourceClass] else SourceClass.AUTHORITATIVE_DOMAIN
        trust_tier = _SOURCE_CLASS_TRUST.get(sc_enum, 3)

        # Build content from entity fields
        name = entity.get("name", "")
        entity_type = entity.get("entity_type", "")
        props = entity.get("properties", "{}")
        if isinstance(props, str):
            props = props
        else:
            import json
            props = json.dumps(props)

        content = f"[{entity_type}] {name}"
        if props and props != "{}":
            content += f"\n{props}"

        path = entity.get("path", [])
        if path:
            path_str = " -> ".join(f"{p.get('rel_type', '')}" for p in path)
            content += f"\nPath: {path_str}"

        grounded.append(GroundedChunk(
            chunk_id=entity.get("entity_id", str(uuid.uuid4())[:12]),
            content=content,
            source_class=source_class,
            entity_type=entity_type,
            trust_tier=trust_tier,
            relevance_score=1.0,  # graph results are structurally relevant
            freshness_status="fresh",
            freshness_flag=False,
            source_document_id="",
            retrieved_at=now,
        ))

    return grounded
