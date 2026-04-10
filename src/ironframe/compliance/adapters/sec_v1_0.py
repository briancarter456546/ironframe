# ============================================================================
# ironframe/compliance/sec_v1_0.py - v1.0
# Last updated: 2026-04-08
# ============================================================================
# SEC compliance adapter for Iron Frame.
# ============================================================================

from typing import Dict

from ironframe.compliance.adapter_base_v1_0 import ComplianceAdapter


class SECAdapter(ComplianceAdapter):
    """U.S. Securities and Exchange Commission compliance mapping adapter."""

    regulation_id = "SEC"
    display_name = "U.S. Securities and Exchange Commission"
    sections: Dict[str, str] = {
        "SEC Rule 17a-4": "Records retention requirements for broker-dealers",
        "SEC Rule 15c3-5": "Market access rule -- risk controls",
        "SEC Reg SCI": "Systems compliance and integrity",
        "SEC Rule 38a-1": "Compliance programs for investment companies",
        "SEC Cybersecurity": "Cybersecurity risk management and incident disclosure",
        "SEC AI Guidance": "Use of AI and automated tools in investment advice",
    }


_SEC_MAPPINGS = {
    "SEC Rule 17a-4": ["IF-REQ-001", "IF-REQ-003", "IF-REQ-017"],
    "SEC Rule 15c3-5": ["IF-REQ-002", "IF-REQ-009", "IF-REQ-011"],
    "SEC Reg SCI": ["IF-REQ-005", "IF-REQ-008", "IF-REQ-011"],
    "SEC Rule 38a-1": ["IF-REQ-001", "IF-REQ-005", "IF-REQ-007"],
    "SEC Cybersecurity": ["IF-REQ-014", "IF-REQ-001", "IF-REQ-011"],
    "SEC AI Guidance": ["IF-REQ-003", "IF-REQ-007", "IF-REQ-018"],
}


def seed_sec_compliance_refs(registry) -> None:
    """Add SEC compliance_refs to RTM entries. Idempotent."""
    for section_id, req_ids in _SEC_MAPPINGS.items():
        for req_id in req_ids:
            entry = registry.get(req_id)
            if entry and section_id not in entry.compliance_refs:
                entry.compliance_refs.append(section_id)
