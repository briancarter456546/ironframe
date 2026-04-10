# ============================================================================
# ironframe/tool_governance/contract_v1_0.py - v1.0
# Last updated: 2026-04-05
# ============================================================================
# Component 12c: Contract Validation
#
# Two-layer validation via Component 16 (correction #1):
#   Layer 1: Governance envelope (tool_id, version, caller_id, resource_id)
#   Layer 2: Per-tool payload (tool.{tool_id}.request/response)
#
# The envelope validates the wrapper. The per-tool schema validates the
# actual parameters. This is where real contract enforcement happens.
# ============================================================================

from dataclasses import dataclass
from typing import Any, Dict, Optional

from ironframe.io_schema.registry_v1_0 import SchemaRegistry
from ironframe.io_schema.validator_v1_0 import validate_boundary, validate_payload
from ironframe.io_schema.errors_v1_0 import ValidationResult, ValidationError, SCHEMA_MISSING, ERROR, WARNING
from ironframe.io_schema.boundaries_v1_0 import BoundaryPoint


@dataclass
class ToolCallContract:
    """Contract metadata for a tool call (beyond schema)."""
    tool_id: str
    idempotent: bool = False
    has_side_effects: bool = True
    rollback_supported: bool = False
    max_latency_ms: int = 30000


class ContractValidator:
    """Validates tool call requests and responses via Component 16.

    Two-layer validation:
      1. Governance envelope (generic across all tools)
      2. Per-tool payload schema (tool-specific parameters)
    """

    def __init__(self, schema_registry: SchemaRegistry, audit_logger=None):
        self._registry = schema_registry
        self._audit = audit_logger

    def validate_request(
        self,
        tool_id: str,
        params: Dict[str, Any],
        governed: bool = True,
        blocking: bool = True,
    ) -> ValidationResult:
        """Validate tool call parameters against per-tool request schema.

        Layer 2 validation: tool.{tool_id}.request schema.
        """
        schema_id = f"tool.{tool_id}.request"
        boundary = BoundaryPoint(
            boundary_id=schema_id,
            component="tool_governance.contract",
            direction="input",
            schema_id=schema_id,
            governed=governed,
            blocking=blocking,
            coercion_policy="permissive",  # tool params often need coercion
            allow_unknown=False,
            audit_event_required=True,
            drift_observation_enabled=True,
        )
        return validate_boundary(
            boundary_id=schema_id,
            payload=params,
            registry=self._registry,
            boundary_point=boundary,
            audit_logger=self._audit,
        )

    def validate_response(
        self,
        tool_id: str,
        result: Dict[str, Any],
        governed: bool = True,
        blocking: bool = False,  # response validation typically non-blocking
    ) -> ValidationResult:
        """Validate tool call response against per-tool response schema.

        Layer 2 validation: tool.{tool_id}.response schema.
        """
        schema_id = f"tool.{tool_id}.response"
        boundary = BoundaryPoint(
            boundary_id=schema_id,
            component="tool_governance.contract",
            direction="output",
            schema_id=schema_id,
            governed=governed,
            blocking=blocking,
            coercion_policy="permissive",
            allow_unknown=True,  # tool responses may include extra data
            audit_event_required=True,
            drift_observation_enabled=True,
        )
        return validate_boundary(
            boundary_id=schema_id,
            payload=result,
            registry=self._registry,
            boundary_point=boundary,
            audit_logger=self._audit,
        )

    def validate_envelope(
        self,
        envelope: Dict[str, Any],
    ) -> ValidationResult:
        """Validate the governance envelope (Layer 1).

        Checks tool_id, version, caller_id, resource_id structure.
        Uses the generic tool.call.envelope schema.
        """
        boundary = BoundaryPoint(
            boundary_id="tool.call.envelope",
            component="tool_governance.contract",
            direction="input",
            schema_id="tool.call.envelope",
            governed=True,
            blocking=True,
            coercion_policy="strict",
            allow_unknown=False,
            audit_event_required=True,
            drift_observation_enabled=False,
        )
        return validate_boundary(
            boundary_id="tool.call.envelope",
            payload=envelope,
            registry=self._registry,
            boundary_point=boundary,
            audit_logger=self._audit,
        )
