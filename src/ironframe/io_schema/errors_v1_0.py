# ============================================================================
# ironframe/io_schema/errors_v1_0.py - v1.0
# Last updated: 2026-04-05
# ============================================================================
# Component 16c: Actionable Error Diagnostics
#
# Field-level validation errors with specific suggestions. Designed so
# Component 8 (Recovery) can build self-correction prompts from structured
# error data rather than generic "schema error" messages.
#
# Constitution reference: Law 6 (no silent bypasses), Law 8 (specs executable)
# RTM: IF-REQ-006 (tool calls must pass schema and governance checks)
# ============================================================================

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Error type constants
MISSING_REQUIRED = "missing_required"
WRONG_TYPE = "wrong_type"
INVALID_ENUM = "invalid_enum"
OUT_OF_RANGE = "out_of_range"
CONSTRAINT_VIOLATED = "constraint_violated"
UNKNOWN_FIELD = "unknown_field"
SCHEMA_MISSING = "schema_missing"
VERSION_MISMATCH = "version_mismatch"

# Severity constants
ERROR = "error"
WARNING = "warning"


@dataclass
class ValidationError:
    """Single field-level validation error with actionable diagnostics.

    Compiler-style: specific field, what went wrong, what was expected,
    and a concrete suggestion for how to fix it.
    """
    field: str              # dotted path: "claims[0].status", "cost_usd", ""
    error_type: str         # one of the constants above
    message: str            # human-readable description
    expected: Any = None    # what was expected (type, value, range)
    received: Any = None    # what was actually received
    suggestion: str = ""    # actionable fix instruction
    severity: str = ERROR   # "error" or "warning"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "error_type": self.error_type,
            "message": self.message,
            "expected": _safe_repr(self.expected),
            "received": _safe_repr(self.received),
            "suggestion": self.suggestion,
            "severity": self.severity,
        }

    def to_retry_hint(self) -> str:
        """One-line hint for Component 8 retry prompt construction."""
        if self.suggestion:
            return f"{self.field}: {self.suggestion}"
        return f"{self.field}: {self.message}"


@dataclass
class ValidationResult:
    """Full result of validating a payload against a schema."""
    valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    coercions: list = field(default_factory=list)  # List[CoercionRecord] from coercion_v1_0
    payload: Dict[str, Any] = field(default_factory=dict)  # possibly coerced
    schema_id: str = ""
    schema_version: str = ""
    boundary_id: str = ""
    outcome: str = ""       # passed, failed, coerced, schema_missing, report_only_warning
    blocking: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "outcome": self.outcome,
            "boundary_id": self.boundary_id,
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "blocking": self.blocking,
            "error_count": len(self.errors),
            "coercion_count": len(self.coercions),
            "errors": [e.to_dict() for e in self.errors],
            "coercions": [c.to_dict() if hasattr(c, "to_dict") else c for c in self.coercions],
        }

    def to_recovery_context(self) -> Dict[str, Any]:
        """Machine-readable recovery context for Component 8 (Recovery Engine).

        Includes boundary_id, schema_id, error codes, and suggested retry strategy.
        """
        field_errors = []
        for e in self.errors:
            field_errors.append({
                "field": e.field,
                "hint": e.suggestion or e.message,
                "error_code": e.error_type,
            })

        # Determine suggested retry strategy from error types
        error_types = {e.error_type for e in self.errors}
        if SCHEMA_MISSING in error_types:
            strategy = "abort"
        elif VERSION_MISMATCH in error_types:
            strategy = "abort"
        elif error_types <= {WRONG_TYPE, INVALID_ENUM, OUT_OF_RANGE, CONSTRAINT_VIOLATED}:
            strategy = "rephrase"
        elif MISSING_REQUIRED in error_types:
            strategy = "rephrase"
        else:
            strategy = "rephrase"

        # Build retry instruction from all errors
        hints = [e.to_retry_hint() for e in self.errors if e.severity == ERROR]
        retry_instruction = ". ".join(hints) if hints else ""

        error_type_summary = ", ".join(
            f"{et} on {e.field}" for e in self.errors for et in [e.error_type]
        )

        return {
            "boundary_id": self.boundary_id,
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "error_count": len(self.errors),
            "blocking": self.blocking,
            "error_summary": f"{len(self.errors)} errors: {error_type_summary}" if self.errors else "No errors",
            "field_errors": field_errors,
            "suggested_retry_strategy": strategy,
            "retry_instruction": retry_instruction,
        }


def format_errors_for_human(errors: List[ValidationError]) -> str:
    """Multi-line human-readable error report."""
    if not errors:
        return "No validation errors."
    lines = [f"Validation errors ({len(errors)}):"]
    for e in errors:
        severity_tag = "[ERROR]" if e.severity == ERROR else "[WARN]"
        lines.append(f"  {severity_tag} {e.field}: {e.message}")
        if e.suggestion:
            lines.append(f"           Fix: {e.suggestion}")
    return "\n".join(lines)


def _safe_repr(val: Any) -> Any:
    """Safe representation for serialization. Truncate long values."""
    if val is None:
        return None
    if isinstance(val, (str, int, float, bool)):
        if isinstance(val, str) and len(val) > 200:
            return val[:200] + "..."
        return val
    if isinstance(val, (list, tuple)):
        if len(val) > 10:
            return list(val[:10]) + ["..."]
        return list(val)
    if isinstance(val, dict):
        return {k: _safe_repr(v) for k, v in list(val.items())[:10]}
    return str(val)[:200]
