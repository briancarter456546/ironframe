# ============================================================================
# ironframe/audit/schema_v1_0.py - v1.0
# Last updated: 2026-04-04
# ============================================================================
# AuditEvent dataclass -- compliance-ready from day 1.
#
# Fields satisfy the union of HIPAA, FINRA, and SOC2 requirements:
#   - HIPAA: input_hash (not raw PHI), retention_class, data_lineage
#   - FINRA: full recordkeeping, cost tracking, 7yr retention
#   - SOC2: component tracing, hook results, change trail
#
# Usage:
#   from ironframe.audit.schema_v1_0 import AuditEvent, ConfidenceBand
#   event = AuditEvent.create(
#       event_type='model_call', component='mal.client',
#       input_text='What is the capital of France?',
#       output_summary='Paris is the capital of France.',
#       model_id='claude-haiku-4-5-20251001', provider='anthropic',
#       tokens_in=12, tokens_out=8, cost_usd=0.0001,
#   )
# ============================================================================

import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class ConfidenceBand(str, Enum):
    """Confidence classification bands."""
    HIGH = "HIGH"              # >0.8 -- proceed without intervention
    MEDIUM = "MEDIUM"          # 0.5-0.8 -- proceed with disclosure
    LOW = "LOW"                # 0.2-0.5 -- retry or escalate
    UNACCEPTABLE = "UNACCEPTABLE"  # <0.2 -- halt, log, alert
    UNSCORED = "UNSCORED"     # no scoring attempted


def _utc_now() -> str:
    """ISO 8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _sha256(text: str) -> str:
    """SHA-256 hash of input text. For PHI/PII safety -- never store raw input."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _new_event_id() -> str:
    """Unique event identifier."""
    return str(uuid.uuid4())


@dataclass
class AuditEvent:
    """Immutable record of a single auditable event in Iron Frame.

    Designed to satisfy HIPAA, FINRA, and SOC2 audit requirements from day 1.
    All fields are populated at creation time. Once created, an AuditEvent
    should never be modified -- only new events appended.
    """

    # --- Identity ---
    event_id: str = ""
    timestamp: str = ""
    session_id: str = ""

    # --- What happened ---
    event_type: str = ""           # model_call, hook_fire, skill_load, escalation, etc.
    component: str = ""            # dotted path: mal.client, sae.judge, audit.logger

    # --- Input (hashed for PHI/PII safety) ---
    input_hash: str = ""           # SHA-256 of raw input
    input_length: int = 0          # character count of raw input

    # --- Output ---
    output_summary: str = ""       # truncated output (configurable max length)
    output_hash: str = ""          # SHA-256 of full output

    # --- Confidence ---
    confidence_score: float = -1.0  # -1.0 = unscored
    confidence_band: str = ConfidenceBand.UNSCORED.value
    confidence_signals: Dict[str, Any] = field(default_factory=dict)

    # --- Model details ---
    model_id: str = ""
    provider: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0

    # --- Hook results ---
    hook_results: List[Dict[str, Any]] = field(default_factory=list)

    # --- Compliance ---
    active_adapters: List[str] = field(default_factory=list)
    retention_class: str = "default"  # compliance adapters override: "6yr", "7yr", etc.
    data_lineage: Dict[str, Any] = field(default_factory=dict)

    # --- Streaming ---
    is_streaming: bool = False
    stream_status: str = ""        # "open", "closed", "error"

    # --- Error ---
    error: str = ""
    error_type: str = ""

    # --- Schema version ---
    schema_version: str = "1.0"

    @classmethod
    def create(
        cls,
        event_type: str,
        component: str,
        session_id: str = "",
        input_text: str = "",
        output_summary: str = "",
        output_text: str = "",
        confidence_score: float = -1.0,
        confidence_signals: Optional[Dict[str, Any]] = None,
        model_id: str = "",
        provider: str = "",
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
        hook_results: Optional[List[Dict[str, Any]]] = None,
        active_adapters: Optional[List[str]] = None,
        retention_class: str = "default",
        data_lineage: Optional[Dict[str, Any]] = None,
        is_streaming: bool = False,
        stream_status: str = "",
        error: str = "",
        error_type: str = "",
        max_summary_len: int = 500,
    ) -> "AuditEvent":
        """Factory method to create a fully populated AuditEvent."""

        # Determine confidence band from score
        if confidence_score < 0:
            band = ConfidenceBand.UNSCORED.value
        elif confidence_score >= 0.8:
            band = ConfidenceBand.HIGH.value
        elif confidence_score >= 0.5:
            band = ConfidenceBand.MEDIUM.value
        elif confidence_score >= 0.2:
            band = ConfidenceBand.LOW.value
        else:
            band = ConfidenceBand.UNACCEPTABLE.value

        # Truncate output summary
        if output_summary and len(output_summary) > max_summary_len:
            output_summary = output_summary[:max_summary_len] + "..."

        return cls(
            event_id=_new_event_id(),
            timestamp=_utc_now(),
            session_id=session_id,
            event_type=event_type,
            component=component,
            input_hash=_sha256(input_text) if input_text else "",
            input_length=len(input_text),
            output_summary=output_summary,
            output_hash=_sha256(output_text) if output_text else "",
            confidence_score=confidence_score,
            confidence_band=band,
            confidence_signals=confidence_signals or {},
            model_id=model_id,
            provider=provider,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            hook_results=hook_results or [],
            active_adapters=active_adapters or [],
            retention_class=retention_class,
            data_lineage=data_lineage or {},
            is_streaming=is_streaming,
            stream_status=stream_status,
            error=error,
            error_type=error_type,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON output."""
        return asdict(self)

    def to_json(self) -> str:
        """Serialize to JSON string (single line, ASCII-safe)."""
        return json.dumps(self.to_dict(), ensure_ascii=True, default=str)
