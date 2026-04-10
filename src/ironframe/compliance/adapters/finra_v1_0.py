# ============================================================================
# ironframe/compliance/finra_v1_0.py - v1.0
# Last updated: 2026-04-08
# ============================================================================
# FINRA compliance adapter for Iron Frame.
#
# Maps FINRA rules to Iron Frame requirements via compliance_refs in the RTM.
# Provides coverage reporting.
# ============================================================================

from typing import Dict

from ironframe.compliance.adapter_base_v1_0 import ComplianceAdapter


class FINRAAdapter(ComplianceAdapter):
    """FINRA rules compliance mapping adapter."""

    regulation_id = "FINRA"
    display_name = "Financial Industry Regulatory Authority"
    sections: Dict[str, str] = {
        "FINRA Rule 4370": "Business continuity plans and emergency contact information",
        "FINRA Rule 3110": "Supervision",
        "FINRA Rule 4511": "General requirements for books and records",
        "FINRA Rule 4512": "Customer account information",
        "FINRA Rule 2010": "Standards of commercial honor and principles of trade",
        "FINRA Rule 4370A": "Annual review and executive approval of BCP",
    }


# Section -> IF-REQ mappings
_FINRA_MAPPINGS = {
    "FINRA Rule 4370": ["IF-REQ-011", "IF-REQ-017"],
    "FINRA Rule 3110": ["IF-REQ-001", "IF-REQ-005", "IF-REQ-007"],
    "FINRA Rule 4511": ["IF-REQ-001", "IF-REQ-003"],
    "FINRA Rule 4512": ["IF-REQ-007", "IF-REQ-017"],
    "FINRA Rule 2010": ["IF-REQ-003", "IF-REQ-005", "IF-REQ-014"],
    "FINRA Rule 4370A": ["IF-REQ-011", "IF-REQ-005"],
}


def seed_finra_compliance_refs(registry) -> None:
    """Add FINRA compliance_refs to RTM entries. Idempotent."""
    for section_id, req_ids in _FINRA_MAPPINGS.items():
        for req_id in req_ids:
            entry = registry.get(req_id)
            if entry and section_id not in entry.compliance_refs:
                entry.compliance_refs.append(section_id)
