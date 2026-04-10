# ============================================================================
# ironframe/kb/write_v1_0.py - v1.0
# Last updated: 2026-04-06
# ============================================================================
# Component 10f: Write Governance
#
# Strictly controlled by source class:
#   Canonical: explicit human approval flag + approver ID required
#   Authoritative Domain: human or policy-approved pipeline
#   Analytical: auto-accepted as status=pending
#   Ephemeral: session-scoped, no approval needed
#
# All writes logged to C7 Audit.
# ============================================================================

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ironframe.kb.storage_v1_0 import KBStore
from ironframe.audit.logger_v1_0 import AuditLogger


class WriteRejected(Exception):
    """Raised when a write is rejected due to missing approval."""
    def __init__(self, source_class: str, reason: str):
        self.source_class = source_class
        super().__init__(f"Write rejected for {source_class}: {reason}")


@dataclass
class WriteResult:
    """Result of a governed write operation."""
    accepted: bool
    entity_id: str = ""
    chunk_id: str = ""
    source_class: str = ""
    status: str = ""          # active, pending, rejected
    rejection_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "entity_id": self.entity_id,
            "chunk_id": self.chunk_id,
            "source_class": self.source_class,
            "status": self.status,
            "rejection_reason": self.rejection_reason,
        }


class WriteGovernor:
    """Enforces write permissions by source class. All writes audited."""

    def __init__(self, store: KBStore, audit_logger: Optional[AuditLogger] = None):
        self._store = store
        self._audit = audit_logger

    def write_chunk(
        self,
        content: str,
        source_class: str,
        entity_type: str = "",
        source_document_id: str = "",
        metadata: Optional[Dict] = None,
        approved: bool = False,
        approver: str = "",
        session_id: str = "",
    ) -> WriteResult:
        """Write a content chunk with governance enforcement."""
        # Check approval
        rejection = self._check_approval(source_class, approved, approver)
        if rejection:
            self._log_write("rejected", "", source_class, rejection, approver, session_id)
            return WriteResult(
                accepted=False, source_class=source_class,
                status="rejected", rejection_reason=rejection,
            )

        # Determine status
        status = "pending" if source_class == "analytical" and not approved else "active"

        chunk_id = self._store.insert_chunk(
            content=content,
            source_class=source_class,
            entity_type=entity_type,
            source_document_id=source_document_id,
            metadata=metadata,
            status=status,
        )

        self._log_write("accepted", chunk_id, source_class, "", approver, session_id)

        return WriteResult(
            accepted=True, chunk_id=chunk_id,
            source_class=source_class, status=status,
        )

    def write_entity(
        self,
        entity_type: str,
        source_class: str,
        name: str = "",
        properties: Optional[Dict] = None,
        approved: bool = False,
        approver: str = "",
        session_id: str = "",
    ) -> WriteResult:
        """Write a graph entity with governance enforcement."""
        rejection = self._check_approval(source_class, approved, approver)
        if rejection:
            self._log_write("rejected", "", source_class, rejection, approver, session_id)
            return WriteResult(
                accepted=False, source_class=source_class,
                status="rejected", rejection_reason=rejection,
            )

        entity_id = self._store.insert_entity(
            entity_type=entity_type,
            source_class=source_class,
            name=name,
            properties=properties,
        )

        self._log_write("accepted", entity_id, source_class, "", approver, session_id)

        return WriteResult(
            accepted=True, entity_id=entity_id,
            source_class=source_class, status="active",
        )

    def write_relationship(
        self,
        from_entity_id: str,
        rel_type: str,
        to_entity_id: str,
        properties: Optional[Dict] = None,
        session_id: str = "",
    ) -> str:
        """Write a graph relationship. No approval needed for relationships."""
        rel_id = self._store.insert_relationship(
            from_entity_id, rel_type, to_entity_id, properties,
        )
        self._log_write("accepted", rel_id, "relationship", "", "", session_id)
        return rel_id

    def _check_approval(self, source_class: str, approved: bool, approver: str) -> str:
        """Check if write is approved for the given source class.

        Returns rejection reason (empty = approved).
        """
        if source_class == "canonical":
            if not approved:
                return "Canonical writes require explicit human approval flag"
            if not approver:
                return "Canonical writes require approver identity"
            return ""

        if source_class == "authoritative_domain":
            if not approved:
                return "Authoritative Domain writes require human or policy approval"
            return ""

        # Analytical and Ephemeral: no approval needed
        return ""

    def _log_write(self, operation: str, entity_id: str, source_class: str,
                   rejection: str, approver: str, session_id: str) -> None:
        if not self._audit:
            return
        try:
            self._audit.log_event(
                event_type="kb.write",
                component="kb.write_governor",
                session_id=session_id,
                details={
                    "operation": operation,
                    "entity_id": entity_id,
                    "source_class": source_class,
                    "approver": approver,
                    "rejection_reason": rejection,
                },
            )
        except Exception:
            pass
