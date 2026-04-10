# ============================================================================
# ironframe/kb/arbitration_v1_0.py - v1.0
# Last updated: 2026-04-06
# ============================================================================
# Component 10d: Truth Arbitration
#
# Triggered when model output contains claims contradicting Canonical or
# Authoritative Domain KB entities. Constitution Law 7: the model never
# silently wins against KB truth.
#
# Addition #3: Arbitration event write to C7 MUST complete before flagged
# output exits C10. If C7 write fails, BLOCK the output — no silent audit gap.
#
# v1 claim extraction: lightweight rule-based. Accuracy limitations accepted.
# ============================================================================

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ironframe.kb.storage_v1_0 import KBStore
from ironframe.audit.logger_v1_0 import AuditLogger


# Contradiction severity
DIRECT_CONFLICT = "direct_factual_conflict"
SOFT_CONFLICT = "soft_conflict"
NO_CONFLICT = "no_conflict"

# Arbitration decisions
BLOCK_HUMAN_REVIEW = "block_human_review"
DOWNGRADE_CONFIDENCE = "downgrade_confidence"
FLAG_ATTACHED = "flag_attached"
PASS_THROUGH = "pass_through"


class ArbitrationAuditFailed(Exception):
    """Raised when C7 audit write fails during arbitration.

    Addition #3: if audit write fails, output is BLOCKED.
    No silent audit gap allowed.
    """
    def __init__(self, claim: str, reason: str):
        super().__init__(
            f"Arbitration audit write failed — output blocked. "
            f"Claim: '{claim[:60]}'. Reason: {reason}"
        )


@dataclass
class ExtractedClaim:
    """A factual assertion extracted from model output."""
    text: str
    position: int = 0


@dataclass
class ArbitrationEvent:
    """Record of a truth arbitration decision.

    Required fields per addition #3: model_claim_text, conflicting_kb_entity_id,
    source_class, severity, decision, session_id, timestamp.
    """
    model_claim_text: str
    conflicting_kb_entity_id: str
    conflicting_kb_content: str
    source_class: str
    severity: str                # direct_factual_conflict, soft_conflict, no_conflict
    decision: str                # block_human_review, downgrade_confidence, flag_attached, pass_through
    session_id: str
    timestamp: str = ""
    confidence_penalty: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_claim_text": self.model_claim_text[:200],
            "conflicting_kb_entity_id": self.conflicting_kb_entity_id,
            "source_class": self.source_class,
            "severity": self.severity,
            "decision": self.decision,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "confidence_penalty": self.confidence_penalty,
        }


@dataclass
class ArbitrationResult:
    """Full result of arbitrating model output against KB truth."""
    has_conflicts: bool
    events: List[ArbitrationEvent] = field(default_factory=list)
    blocked: bool = False
    total_confidence_penalty: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_conflicts": self.has_conflicts,
            "event_count": len(self.events),
            "blocked": self.blocked,
            "total_confidence_penalty": round(self.total_confidence_penalty, 3),
            "events": [e.to_dict() for e in self.events],
        }


# ============================================================================
# CLAIM EXTRACTION (v1: lightweight rule-based)
# ============================================================================

# Patterns that indicate factual assertions
_ASSERTION_PATTERNS = [
    r"(?:^|\. )([A-Z][^.?!]*(?:is|are|was|were|has|have|does|do|will|can|should|must)[^.?!]*\.)",
    r"(?:^|\. )(The [^.?!]+(?:is|are|was|were)[^.?!]*\.)",
    r"(?:^|\. )([^.?!]+ (?:equals?|costs?|measures?|contains?|requires?|produces?)[^.?!]*\.)",
]


def extract_claims(text: str) -> List[ExtractedClaim]:
    """Extract factual assertions from text.

    v1: regex-based extraction. Gets declarative sentences with
    copula/factual verbs. Accuracy is limited — acceptable for v1.
    """
    claims = []
    seen = set()

    for pattern in _ASSERTION_PATTERNS:
        for match in re.finditer(pattern, text):
            claim_text = match.group(1).strip()
            if len(claim_text) > 20 and claim_text not in seen:
                seen.add(claim_text)
                claims.append(ExtractedClaim(text=claim_text, position=match.start()))

    # Also split by sentences and take declarative ones
    sentences = re.split(r'(?<=[.!?])\s+', text)
    for i, sent in enumerate(sentences):
        sent = sent.strip()
        if (len(sent) > 20 and sent not in seen
                and not sent.endswith("?")
                and any(v in sent.lower() for v in ["is ", "are ", "was ", "has ", "the "])):
            seen.add(sent)
            claims.append(ExtractedClaim(text=sent, position=i))

    return claims[:20]  # cap at 20 claims to bound cost


# ============================================================================
# CONTRADICTION DETECTION
# ============================================================================

def _check_contradiction(claim: str, kb_content: str) -> str:
    """Simple contradiction check between a claim and KB content.

    v1: keyword overlap + negation detection. Not semantic.
    Returns severity: direct_factual_conflict, soft_conflict, or no_conflict.
    """
    claim_lower = claim.lower()
    kb_lower = kb_content.lower()

    # Extract key terms from both
    claim_words = set(claim_lower.split())
    kb_words = set(kb_lower.split())
    overlap = claim_words & kb_words

    # Need meaningful overlap to even compare
    meaningful_overlap = {w for w in overlap if len(w) > 3}
    if len(meaningful_overlap) < 2:
        return NO_CONFLICT

    # Check for negation patterns that flip meaning
    negation_words = {"not", "no", "never", "neither", "nor", "isn't", "aren't",
                      "wasn't", "weren't", "doesn't", "don't", "didn't", "cannot",
                      "can't", "won't", "shouldn't", "wouldn't"}

    claim_has_neg = bool(claim_words & negation_words)
    kb_has_neg = bool(kb_words & negation_words)

    # If one has negation and the other doesn't on overlapping topic
    if claim_has_neg != kb_has_neg and len(meaningful_overlap) >= 3:
        return DIRECT_CONFLICT

    # Check for contradictory number/value patterns
    claim_numbers = set(re.findall(r'\b\d+\.?\d*\b', claim))
    kb_numbers = set(re.findall(r'\b\d+\.?\d*\b', kb_content))
    if claim_numbers and kb_numbers and len(meaningful_overlap) >= 3:
        if claim_numbers != kb_numbers and not claim_numbers.issubset(kb_numbers):
            return SOFT_CONFLICT

    return NO_CONFLICT


# ============================================================================
# TRUTH ARBITRATOR
# ============================================================================

class TruthArbitrator:
    """Arbitrates between model output and KB truth.

    Constitution Law 7: model never silently wins against KB truth.
    Addition #3: audit write must complete before flagged output exits.
    """

    def __init__(self, store: KBStore, audit_logger: Optional[AuditLogger] = None):
        self._store = store
        self._audit = audit_logger

    def arbitrate(
        self,
        model_output: str,
        session_id: str = "",
        source_classes: Optional[List[str]] = None,
    ) -> ArbitrationResult:
        """Check model output against KB truth.

        Extracts claims, compares against Canonical and Authoritative Domain,
        logs arbitration events, returns result.
        """
        if source_classes is None:
            source_classes = ["canonical", "authoritative_domain"]

        claims = extract_claims(model_output)
        if not claims:
            return ArbitrationResult(has_conflicts=False)

        events = []
        blocked = False
        total_penalty = 0.0

        for claim in claims:
            # Search KB for relevant content
            kb_results = self._store.search_chunks_semantic(
                claim.text, top_k=3, source_classes=source_classes,
            )

            for kb_chunk in kb_results:
                severity = _check_contradiction(claim.text, kb_chunk.get("content", ""))
                if severity == NO_CONFLICT:
                    continue

                kb_source_class = kb_chunk.get("source_class", "")

                # Determine decision based on severity + source class
                if severity == DIRECT_CONFLICT and kb_source_class == "canonical":
                    decision = BLOCK_HUMAN_REVIEW
                    penalty = 0.5
                    blocked = True
                elif severity == DIRECT_CONFLICT:
                    decision = DOWNGRADE_CONFIDENCE
                    penalty = 0.3
                elif severity == SOFT_CONFLICT:
                    decision = FLAG_ATTACHED
                    penalty = 0.1
                else:
                    continue

                total_penalty += penalty

                event = ArbitrationEvent(
                    model_claim_text=claim.text,
                    conflicting_kb_entity_id=kb_chunk.get("chunk_id", ""),
                    conflicting_kb_content=kb_chunk.get("content", "")[:200],
                    source_class=kb_source_class,
                    severity=severity,
                    decision=decision,
                    session_id=session_id,
                    confidence_penalty=penalty,
                )
                events.append(event)

                # Addition #3: write audit event BEFORE output can exit
                # If audit write fails, block the output
                self._write_arbitration_event(event, claim.text)

        return ArbitrationResult(
            has_conflicts=len(events) > 0,
            events=events,
            blocked=blocked,
            total_confidence_penalty=total_penalty,
        )

    def _write_arbitration_event(self, event: ArbitrationEvent, claim_text: str) -> None:
        """Write arbitration event to C7. MUST complete before output exits.

        Addition #3: if write fails, raise ArbitrationAuditFailed to block output.
        """
        if not self._audit:
            return

        try:
            self._audit.log_event(
                event_type="kb.arbitration",
                component="kb.arbitration",
                session_id=event.session_id,
                details={
                    "model_claim_text": event.model_claim_text[:200],
                    "conflicting_kb_entity_id": event.conflicting_kb_entity_id,
                    "source_class": event.source_class,
                    "severity": event.severity,
                    "decision": event.decision,
                    "confidence_penalty": event.confidence_penalty,
                    "timestamp": event.timestamp,
                },
            )
        except Exception as exc:
            # Addition #3: audit failure = block output
            raise ArbitrationAuditFailed(claim_text, str(exc))
