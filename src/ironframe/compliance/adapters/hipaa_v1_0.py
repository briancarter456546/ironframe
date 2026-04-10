# ============================================================================
# ironframe/compliance/hipaa_v1_0.py - v1.0
# Last updated: 2026-04-08
# ============================================================================
# HIPAA compliance adapter for Iron Frame.
#
# Maps HIPAA Security Rule sections to Iron Frame requirements via
# compliance_refs in the RTM. Provides coverage reporting.
# ============================================================================

from typing import Dict

from ironframe.compliance.adapter_base_v1_0 import ComplianceAdapter


class HIPAAAdapter(ComplianceAdapter):
    """HIPAA Security Rule compliance mapping adapter."""

    regulation_id = "HIPAA"
    display_name = "Health Insurance Portability and Accountability Act"
    sections: Dict[str, str] = {
        "HIPAA \u00a7164.306": "Security standards: general rules",
        "HIPAA \u00a7164.308": "Administrative safeguards",
        "HIPAA \u00a7164.310": "Physical safeguards",
        "HIPAA \u00a7164.312": "Technical safeguards",
        "HIPAA \u00a7164.314": "Organizational requirements",
        "HIPAA \u00a7164.316": "Policies and procedures and documentation requirements",
        "HIPAA \u00a7164.528": "Accounting of disclosures",
    }


# Section -> IF-REQ mappings
_HIPAA_MAPPINGS = {
    "HIPAA \u00a7164.306": ["IF-REQ-001", "IF-REQ-005", "IF-REQ-008"],
    "HIPAA \u00a7164.308": ["IF-REQ-001", "IF-REQ-007", "IF-REQ-011"],
    "HIPAA \u00a7164.310": ["IF-REQ-002", "IF-REQ-008"],
    "HIPAA \u00a7164.312": ["IF-REQ-002", "IF-REQ-014", "IF-REQ-017"],
    "HIPAA \u00a7164.314": ["IF-REQ-005", "IF-REQ-006"],
    "HIPAA \u00a7164.316": ["IF-REQ-001", "IF-REQ-005"],
    "HIPAA \u00a7164.528": ["IF-REQ-001", "IF-REQ-003"],
}


def seed_hipaa_compliance_refs(registry) -> None:
    """Add HIPAA compliance_refs to RTM entries. Idempotent."""
    for section_id, req_ids in _HIPAA_MAPPINGS.items():
        for req_id in req_ids:
            entry = registry.get(req_id)
            if entry and section_id not in entry.compliance_refs:
                entry.compliance_refs.append(section_id)
