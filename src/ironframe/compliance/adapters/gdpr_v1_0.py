# ============================================================================
# ironframe/compliance/gdpr_v1_0.py - v1.0
# Last updated: 2026-04-08
# ============================================================================
# GDPR compliance adapter for Iron Frame.
# ============================================================================

from typing import Dict

from ironframe.compliance.adapter_base_v1_0 import ComplianceAdapter


class GDPRAdapter(ComplianceAdapter):
    """General Data Protection Regulation compliance mapping adapter."""

    regulation_id = "GDPR"
    display_name = "General Data Protection Regulation"
    sections: Dict[str, str] = {
        "GDPR Art.5": "Principles relating to processing of personal data",
        "GDPR Art.6": "Lawfulness of processing",
        "GDPR Art.17": "Right to erasure",
        "GDPR Art.22": "Automated individual decision-making",
        "GDPR Art.25": "Data protection by design and by default",
        "GDPR Art.30": "Records of processing activities",
        "GDPR Art.32": "Security of processing",
        "GDPR Art.33": "Notification of personal data breach",
        "GDPR Art.35": "Data protection impact assessment",
    }


_GDPR_MAPPINGS = {
    "GDPR Art.5": ["IF-REQ-001", "IF-REQ-003", "IF-REQ-005"],
    "GDPR Art.6": ["IF-REQ-002", "IF-REQ-007"],
    "GDPR Art.17": ["IF-REQ-017"],
    "GDPR Art.22": ["IF-REQ-003", "IF-REQ-007", "IF-REQ-018"],
    "GDPR Art.25": ["IF-REQ-002", "IF-REQ-005", "IF-REQ-014"],
    "GDPR Art.30": ["IF-REQ-001", "IF-REQ-005"],
    "GDPR Art.32": ["IF-REQ-002", "IF-REQ-014", "IF-REQ-017"],
    "GDPR Art.33": ["IF-REQ-001", "IF-REQ-011", "IF-REQ-014"],
    "GDPR Art.35": ["IF-REQ-003", "IF-REQ-005", "IF-REQ-018"],
}


def seed_gdpr_compliance_refs(registry) -> None:
    """Add GDPR compliance_refs to RTM entries. Idempotent."""
    for section_id, req_ids in _GDPR_MAPPINGS.items():
        for req_id in req_ids:
            entry = registry.get(req_id)
            if entry and section_id not in entry.compliance_refs:
                entry.compliance_refs.append(section_id)
