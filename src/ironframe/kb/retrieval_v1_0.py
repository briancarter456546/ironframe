# ============================================================================
# ironframe/kb/retrieval_v1_0.py - v1.0
# Last updated: 2026-04-06
# ============================================================================
# Component 10b: Retrieval Engine
#
# Two modes: semantic (vector search) and graph (adjacency traversal).
# Hybrid (default for complex queries): both modes, results merged.
#
# Graph traversal max_hops is configurable (addition #2), default=3.
# ============================================================================

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from ironframe.kb.storage_v1_0 import KBStore
from ironframe.kb.freshness_v1_0 import check_freshness


class RetrievalMode(str, Enum):
    SEMANTIC = "semantic"
    GRAPH = "graph"
    HYBRID = "hybrid"


@dataclass
class RetrievalResult:
    """Result from a single retrieval operation."""
    mode: str
    query: str
    chunks: List[Dict[str, Any]] = field(default_factory=list)
    entities: List[Dict[str, Any]] = field(default_factory=list)
    total_results: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "query": self.query[:100],
            "chunk_count": len(self.chunks),
            "entity_count": len(self.entities),
            "total_results": self.total_results,
        }


class RetrievalEngine:
    """Dual-mode retrieval: semantic + graph, with hybrid merge."""

    def __init__(self, store: KBStore, default_max_hops: int = 3):
        self._store = store
        self._default_max_hops = default_max_hops

    def retrieve(
        self,
        query: str,
        mode: str = "hybrid",
        top_k: int = 10,
        source_classes: Optional[List[str]] = None,
        entity_type: str = "",
        rel_type: str = "",
        start_entity_id: str = "",
        max_hops: Optional[int] = None,
        governed: bool = False,
    ) -> RetrievalResult:
        """Unified retrieval interface.

        mode: 'semantic', 'graph', or 'hybrid'
        governed: if True, restrict to canonical + authoritative_domain
        max_hops: configurable graph depth (addition #2), defaults to self._default_max_hops
        """
        if max_hops is None:
            max_hops = self._default_max_hops

        # Governed scope restriction
        if governed:
            source_classes = ["canonical", "authoritative_domain"]

        if mode == RetrievalMode.SEMANTIC.value:
            return self._semantic_retrieve(query, top_k, source_classes)
        elif mode == RetrievalMode.GRAPH.value:
            return self._graph_retrieve(query, start_entity_id, rel_type, max_hops)
        else:
            return self._hybrid_retrieve(query, top_k, source_classes,
                                          start_entity_id, rel_type, max_hops)

    def _semantic_retrieve(self, query: str, top_k: int,
                            source_classes: Optional[List[str]]) -> RetrievalResult:
        """Semantic search via cosine similarity."""
        chunks = self._store.search_chunks_semantic(query, top_k, source_classes)

        # Attach freshness info to each chunk
        for chunk in chunks:
            fc = check_freshness(
                chunk.get("chunk_id", ""),
                chunk.get("source_class", ""),
                chunk.get("last_verified_at", ""),
            )
            chunk["freshness_status"] = fc.freshness_status
            chunk["freshness_flag"] = fc.is_stale
            chunk["stale_action"] = fc.stale_action

        return RetrievalResult(
            mode="semantic",
            query=query,
            chunks=chunks,
            total_results=len(chunks),
        )

    def _graph_retrieve(self, query: str, start_entity_id: str,
                         rel_type: str, max_hops: int) -> RetrievalResult:
        """Graph traversal via adjacency tables."""
        if not start_entity_id:
            # Try to find entity by name match
            conn = self._store._get_conn()
            row = conn.execute(
                "SELECT entity_id FROM kb_entities WHERE name LIKE ? LIMIT 1",
                (f"%{query}%",),
            ).fetchone()
            if row:
                start_entity_id = row[0]
            else:
                return RetrievalResult(mode="graph", query=query)

        entities = self._store.traverse(start_entity_id, rel_type, max_hops=max_hops)

        return RetrievalResult(
            mode="graph",
            query=query,
            entities=entities,
            total_results=len(entities),
        )

    def _hybrid_retrieve(self, query: str, top_k: int,
                          source_classes: Optional[List[str]],
                          start_entity_id: str, rel_type: str,
                          max_hops: int) -> RetrievalResult:
        """Hybrid: run both modes, merge results."""
        sem = self._semantic_retrieve(query, top_k, source_classes)
        graph = self._graph_retrieve(query, start_entity_id, rel_type, max_hops)

        return RetrievalResult(
            mode="hybrid",
            query=query,
            chunks=sem.chunks,
            entities=graph.entities,
            total_results=len(sem.chunks) + len(graph.entities),
        )
