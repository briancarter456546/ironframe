# ============================================================================
# ironframe/compliance/base_v1_0.py - v1.0
# Last updated: 2026-04-04
# ============================================================================
# Base compliance adapter contract for Iron Frame.
#
# Each compliance adapter is a skill + hook bundle:
#   - on_input(): process/redact input before model call
#   - on_output(): validate/filter output before release
#   - get_hooks(): return hooks this adapter registers
#   - get_audit_requirements(): what this protocol demands of the audit schema
#
# Adapters register with the Hook Engine on load. New regulatory protocols
# can be added without modifying Iron Frame core.
#
# Usage:
#   from ironframe.compliance.base_v1_0 import ComplianceAdapter
#
#   class HIPAAAdapter(ComplianceAdapter):
#       name = 'hipaa'
#       def on_input(self, text, context):
#           return redact_phi(text), context
#       ...
# ============================================================================

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class ComplianceAdapter(ABC):
    """Base class for compliance protocol adapters.

    Subclasses implement protocol-specific enforcement.
    The audit schema already captures the union of all protocol requirements
    from day 1 -- adapters interpret and enforce the rules.
    """

    name: str = ""                    # e.g., 'hipaa', 'finra', 'soc2'
    description: str = ""
    retention_class: str = "default"  # e.g., '6yr', '7yr'
    min_verification_tier: int = 0    # minimum SAE tier for this protocol

    @abstractmethod
    def on_input(self, text: str, context: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Process input before it reaches the model.

        Returns (processed_text, updated_context).
        Use for: PHI redaction, PII masking, input validation.
        """
        ...

    @abstractmethod
    def on_output(self, text: str, context: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Validate/filter output before release to caller.

        Returns (processed_text, updated_context).
        Use for: prohibited content filtering, customer-output review gates.
        """
        ...

    def get_hooks(self) -> List[Dict[str, Any]]:
        """Return hook definitions this adapter registers.

        Each hook dict: {event, handler, blocking, description}
        Default: empty (adapter uses on_input/on_output only).
        Override to add protocol-specific hook gates.
        """
        return []

    def get_audit_requirements(self) -> Dict[str, Any]:
        """Return what this protocol demands of the audit schema.

        Returns dict describing required fields, retention, access controls.
        Used by the audit system to validate completeness.
        """
        return {
            "name": self.name,
            "retention_class": self.retention_class,
            "min_verification_tier": self.min_verification_tier,
            "required_fields": [],
            "prohibited_in_logs": [],
        }

    def validate_audit_event(self, event_dict: Dict[str, Any]) -> List[str]:
        """Check if an audit event satisfies this protocol's requirements.

        Returns list of violations (empty = compliant).
        Default implementation checks required fields exist and are non-empty.
        """
        requirements = self.get_audit_requirements()
        violations = []

        for field_name in requirements.get("required_fields", []):
            val = event_dict.get(field_name)
            if val is None or val == "" or val == []:
                violations.append(f"Missing required field: {field_name}")

        for field_name in requirements.get("prohibited_in_logs", []):
            if event_dict.get(field_name):
                violations.append(f"Prohibited field present in log: {field_name}")

        return violations
