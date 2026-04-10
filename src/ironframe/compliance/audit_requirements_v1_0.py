# ============================================================================
# ironframe/compliance/audit_requirements_v1_0.py - v1.0
# Last updated: 2026-04-04
# ============================================================================
# Documents what each compliance protocol demands of the audit schema.
#
# CriticMode correction: compliance shapes audit from day 1, not as a bolt-on.
# The audit schema (schema_v1_0.py) captures the UNION of all these requirements.
# This file makes those requirements explicit and testable.
#
# Usage:
#   from ironframe.compliance.audit_requirements_v1_0 import (
#       HIPAA_REQUIREMENTS, FINRA_REQUIREMENTS, SOC2_REQUIREMENTS,
#       get_all_required_fields,
#   )
# ============================================================================

from typing import Dict, Any, List, Set

# ---- HIPAA (Health Insurance Portability and Accountability Act) ----
HIPAA_REQUIREMENTS = {
    "name": "hipaa",
    "description": "Health data privacy and security. PHI must never be stored in raw form.",
    "retention_class": "6yr",
    "min_verification_tier": 2,
    "required_fields": [
        "event_id",
        "timestamp",
        "session_id",
        "event_type",
        "component",
        "input_hash",           # SHA-256, NOT raw input (PHI safety)
        "output_hash",          # SHA-256, NOT raw output
        "model_id",
        "provider",
        "confidence_score",
        "confidence_band",
        "active_adapters",
        "retention_class",
        "data_lineage",
    ],
    "prohibited_in_logs": [
        # Raw text fields that could contain PHI must not be stored
        # input_hash replaces raw input; output_summary is truncated/scrubbed
    ],
    "rules": [
        "PHI detection and redaction BEFORE model input",
        "Input stored as SHA-256 hash only, never raw text",
        "AES-256 encryption enforcement on stored logs",
        "Role-based access validation on log reads",
        "Immutable audit log entries with full data lineage",
        "Breach detection flags on anomalous access patterns",
        "Minimum-necessary access enforcement",
        "6-year retention minimum",
    ],
}

# ---- FINRA (Financial Industry Regulatory Authority) ----
FINRA_REQUIREMENTS = {
    "name": "finra",
    "description": "Financial recordkeeping completeness and customer-output review.",
    "retention_class": "7yr",
    "min_verification_tier": 1,
    "required_fields": [
        "event_id",
        "timestamp",
        "session_id",
        "event_type",
        "component",
        "input_hash",
        "output_summary",       # FINRA needs reviewable output records
        "output_hash",
        "model_id",
        "provider",
        "tokens_in",
        "tokens_out",
        "cost_usd",            # transaction trail
        "confidence_score",
        "confidence_band",
        "hook_results",        # enforcement trail
        "active_adapters",
        "retention_class",
        "data_lineage",
    ],
    "prohibited_in_logs": [],
    "rules": [
        "Recordkeeping completeness -- every model interaction logged",
        "Customer-facing output review gates before release",
        "Transaction audit trail with cost tracking",
        "Prohibited content filters on financial advice",
        "7-year retention minimum",
        "Output must be reproducible from audit trail",
    ],
}

# ---- SOC2 (Service Organization Control Type 2) ----
SOC2_REQUIREMENTS = {
    "name": "soc2",
    "description": "Security, availability, processing integrity, confidentiality, privacy.",
    "retention_class": "default",
    "min_verification_tier": 0,
    "required_fields": [
        "event_id",
        "timestamp",
        "session_id",
        "event_type",
        "component",
        "model_id",
        "provider",
        "hook_results",        # change management trail
        "active_adapters",
        "error",
        "error_type",
    ],
    "prohibited_in_logs": [],
    "rules": [
        "Access control logging on all system interactions",
        "Change management trail (hook results, config changes)",
        "Availability monitoring -- error rates, circuit breaker states",
        "Processing integrity -- confidence scores, verification tiers",
        "Confidentiality -- input hashing, output summary truncation",
    ],
}

# ---- Registry ----
ALL_PROTOCOLS: Dict[str, Dict[str, Any]] = {
    "hipaa": HIPAA_REQUIREMENTS,
    "finra": FINRA_REQUIREMENTS,
    "soc2": SOC2_REQUIREMENTS,
}


def get_all_required_fields() -> Set[str]:
    """Return the union of all required fields across all protocols.

    The audit schema must capture ALL of these fields to be
    compliance-ready from day 1.
    """
    fields: Set[str] = set()
    for protocol in ALL_PROTOCOLS.values():
        fields.update(protocol.get("required_fields", []))
    return fields


def validate_schema_coverage(schema_fields: Set[str]) -> Dict[str, List[str]]:
    """Check if a set of schema fields covers all protocol requirements.

    Returns dict of protocol -> list of missing fields.
    Empty lists = full coverage.
    """
    gaps = {}
    for name, protocol in ALL_PROTOCOLS.items():
        required = set(protocol.get("required_fields", []))
        missing = required - schema_fields
        gaps[name] = sorted(missing)
    return gaps
