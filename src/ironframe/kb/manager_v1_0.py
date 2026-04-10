# ============================================================================
# ironframe/kb/manager_v1_0.py - v1.0
# Last updated: 2026-04-06
# ============================================================================
# Component 10 Orchestrator: KBGroundingLayer
#
# Unified interface: retrieve(), ground(), arbitrate().
# Sits between content sources and C9's RETRIEVED_CONTEXT zone.
#
# Enforces retrieval policy, freshness flagging, truth arbitration,
# write governance, and provenance attachment.
# ============================================================================

from typing import Any, Dict, List, Optional

from ironframe.kb.storage_v1_0 import KBStore, HashEmbedder, EmbeddingProvider
from ironframe.kb.retrieval_v1_0 import RetrievalEngine, RetrievalResult
from ironframe.kb.grounding_v1_0 import GroundedChunk, ground_chunks, ground_entities, SourceClass
from ironframe.kb.arbitration_v1_0 import TruthArbitrator, ArbitrationResult
from ironframe.kb.freshness_v1_0 import check_freshness
from ironframe.kb.write_v1_0 import WriteGovernor, WriteResult
from ironframe.kb.policy_v1_0 import RetrievalPolicyEnforcer, RetrievalPolicy
from ironframe.audit.logger_v1_0 import AuditLogger


class KBGroundingLayer:
    """Component 10 orchestrator.

    Provides retrieve_and_ground() for the standard path:
    query -> retrieve -> policy check -> ground -> attach provenance -> return C9-ready chunks

    Provides arbitrate() for truth checking:
    model output -> extract claims -> compare KB -> log events -> return result
    """

    def __init__(
        self,
        db_path: str = "ironframe/kb/ironframe_kb.db",
        embedder: Optional[EmbeddingProvider] = None,
        audit_logger: Optional[AuditLogger] = None,
        default_max_hops: int = 3,
    ):
        self._store = KBStore(db_path=db_path, embedder=embedder or HashEmbedder())
        self._retrieval = RetrievalEngine(self._store, default_max_hops=default_max_hops)
        self._arbitrator = TruthArbitrator(self._store, audit_logger)
        self._writer = WriteGovernor(self._store, audit_logger)
        self._policy = RetrievalPolicyEnforcer(audit_logger)
        self._audit = audit_logger

    @property
    def store(self) -> KBStore:
        return self._store

    @property
    def writer(self) -> WriteGovernor:
        return self._writer

    def retrieve_and_ground(
        self,
        query: str,
        mode: str = "hybrid",
        top_k: int = 10,
        governed: bool = False,
        agent_autonomy_tier: int = 4,
        max_hops: Optional[int] = None,
        start_entity_id: str = "",
        rel_type: str = "",
        session_id: str = "",
    ) -> List[GroundedChunk]:
        """Standard retrieval path: query -> retrieve -> policy -> ground.

        Returns C9-ready GroundedChunks with trust tier, freshness, provenance.
        """
        # Build policy
        policy = self._policy.get_policy(governed=governed, agent_autonomy_tier=agent_autonomy_tier)

        # Retrieve
        result = self._retrieval.retrieve(
            query=query,
            mode=mode,
            top_k=top_k,
            source_classes=policy.allowed_classes,
            start_entity_id=start_entity_id,
            rel_type=rel_type,
            max_hops=max_hops,
            governed=governed,
        )

        # Policy check on results
        if result.chunks:
            result_classes = [c.get("source_class", "") for c in result.chunks]
            violations = self._policy.check_scope(policy, result_classes, session_id)
            if violations:
                # Filter out violating chunks
                result.chunks = self._policy.filter_by_policy(result.chunks, policy)

        # Ground chunks (assign trust tiers, freshness)
        grounded = []
        if result.chunks:
            grounded.extend(ground_chunks(result.chunks))
        if result.entities:
            grounded.extend(ground_entities(result.entities))

        # Log retrieval
        self._log_retrieval(query, mode, len(grounded), governed, session_id)

        return grounded

    def arbitrate(
        self,
        model_output: str,
        session_id: str = "",
    ) -> ArbitrationResult:
        """Truth arbitration: check model output against KB truth.

        Constitution Law 7: model never silently wins.
        Addition #3: audit write completes before flagged output exits.
        """
        return self._arbitrator.arbitrate(model_output, session_id)

    def write_chunk(self, **kwargs) -> WriteResult:
        """Governed chunk write. Delegates to WriteGovernor."""
        return self._writer.write_chunk(**kwargs)

    def write_entity(self, **kwargs) -> WriteResult:
        """Governed entity write. Delegates to WriteGovernor."""
        return self._writer.write_entity(**kwargs)

    def to_c9_format(self, grounded: List[GroundedChunk]) -> List[Dict[str, Any]]:
        """Convert GroundedChunks to C9 RETRIEVED_CONTEXT zone format."""
        return [g.to_c9_dict() for g in grounded]

    def summary(self) -> Dict[str, Any]:
        return {
            "store": self._store.summary(),
        }

    def close(self) -> None:
        self._store.close()

    def _log_retrieval(self, query: str, mode: str, result_count: int,
                       governed: bool, session_id: str) -> None:
        if not self._audit:
            return
        try:
            self._audit.log_event(
                event_type="kb.retrieval",
                component="kb.manager",
                session_id=session_id,
                details={
                    "query": query[:100],
                    "mode": mode,
                    "result_count": result_count,
                    "governed": governed,
                },
            )
        except Exception:
            pass
