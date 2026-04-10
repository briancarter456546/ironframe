# ============================================================================
# ironframe/compliance/soc2_v1_0.py - v1.0
# Last updated: 2026-04-08
# ============================================================================
# SOC 2 Trust Services Criteria compliance adapter for Iron Frame.
# ============================================================================

from typing import Dict

from ironframe.compliance.adapter_base_v1_0 import ComplianceAdapter


class SOC2Adapter(ComplianceAdapter):
    """SOC 2 Trust Services Criteria compliance mapping adapter."""

    regulation_id = "SOC2"
    display_name = "SOC 2 Trust Services Criteria"
    sections: Dict[str, str] = {
        "SOC2 CC6.1": "Logical and physical access controls",
        "SOC2 CC6.2": "Prior to issuing system credentials and granting access",
        "SOC2 CC6.3": "Role-based access and least privilege",
        "SOC2 CC7.1": "Detection and monitoring of security events",
        "SOC2 CC7.2": "Evaluation of security events",
        "SOC2 CC7.3": "Response to identified security incidents",
        "SOC2 CC8.1": "Change management controls",
        "SOC2 A1.1": "Availability: performance monitoring and capacity planning",
        "SOC2 A1.2": "Availability: recovery and business continuity",
    }


_SOC2_MAPPINGS = {
    "SOC2 CC6.1": ["IF-REQ-002", "IF-REQ-007", "IF-REQ-014"],
    "SOC2 CC6.2": ["IF-REQ-007", "IF-REQ-017"],
    "SOC2 CC6.3": ["IF-REQ-002", "IF-REQ-007"],
    "SOC2 CC7.1": ["IF-REQ-001", "IF-REQ-005", "IF-REQ-014"],
    "SOC2 CC7.2": ["IF-REQ-003", "IF-REQ-005", "IF-REQ-018"],
    "SOC2 CC7.3": ["IF-REQ-011", "IF-REQ-014"],
    "SOC2 CC8.1": ["IF-REQ-005", "IF-REQ-008"],
    "SOC2 A1.1": ["IF-REQ-006", "IF-REQ-009", "IF-REQ-010"],
    "SOC2 A1.2": ["IF-REQ-011", "IF-REQ-017"],
}


def seed_soc2_compliance_refs(registry) -> None:
    """Add SOC 2 compliance_refs to RTM entries. Idempotent."""
    for section_id, req_ids in _SOC2_MAPPINGS.items():
        for req_id in req_ids:
            entry = registry.get(req_id)
            if entry and section_id not in entry.compliance_refs:
                entry.compliance_refs.append(section_id)
