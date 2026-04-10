# ============================================================================
# ironframe/io_schema/validator_v1_0.py - v1.0
# Last updated: 2026-04-05
# ============================================================================
# Component 16b: Core Validation Engine
#
# validate_payload(): checks a dict against a SchemaDefinition
# validate_boundary(): full boundary validation with registry lookup,
#   version checking, coercion, drift observation, and audit logging.
#
# Constitution: Law 6 (no silent bypasses), Output Release Rule 2
# (required schemas validated). Missing schema on governed boundaries
# is a hard fail, not graceful degradation (correction #1).
# ============================================================================

import re
from typing import Any, Dict, List, Optional

from ironframe.io_schema.errors_v1_0 import (
    ValidationError, ValidationResult,
    MISSING_REQUIRED, WRONG_TYPE, INVALID_ENUM, OUT_OF_RANGE,
    CONSTRAINT_VIOLATED, UNKNOWN_FIELD, SCHEMA_MISSING, VERSION_MISMATCH,
    ERROR, WARNING,
)
from ironframe.io_schema.coercion_v1_0 import (
    CoercionPolicy, CoercionMode, CoercionRecord, try_coerce, _classify_type,
)
from ironframe.io_schema.registry_v1_0 import SchemaDefinition, SchemaRegistry, FieldSpec


# Type mapping: schema type names -> Python type checks
_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "float": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "bool": lambda v: isinstance(v, bool),
    "list": lambda v: isinstance(v, list),
    "dict": lambda v: isinstance(v, dict),
    "enum": lambda v: isinstance(v, str),  # enum values checked separately
    "any": lambda v: True,
}


def validate_payload(
    payload: Dict[str, Any],
    schema: SchemaDefinition,
    policy: Optional[CoercionPolicy] = None,
) -> ValidationResult:
    """Validate a payload dict against a schema definition.

    Returns ValidationResult with field-level errors, coercion records,
    and the (possibly coerced) payload.
    """
    if policy is None:
        policy = CoercionPolicy.strict()

    errors: List[ValidationError] = []
    coercions: List[CoercionRecord] = []
    result_payload = dict(payload)  # work on a copy

    # 1. Check required fields
    for field_name in schema.required:
        if field_name not in payload or payload[field_name] is None:
            field_spec = schema.get_field(field_name)
            expected_type = field_spec.field_type if field_spec else "unknown"
            errors.append(ValidationError(
                field=field_name,
                error_type=MISSING_REQUIRED,
                message=f"Required field '{field_name}' is missing",
                expected=expected_type,
                received=None,
                suggestion=f"Include '{field_name}' ({expected_type}) in the output",
            ))

    # 2. Check each present field against its spec
    for field_name, value in payload.items():
        field_spec = schema.get_field(field_name)

        # Unknown field check
        if field_spec is None:
            if policy.mode == CoercionMode.STRICT and not policy.allow_unknown:
                errors.append(ValidationError(
                    field=field_name,
                    error_type=UNKNOWN_FIELD,
                    message=f"Unknown field '{field_name}' not in schema",
                    expected="(not present)",
                    received=type(value).__name__,
                    suggestion=f"Remove '{field_name}' or update the schema to include it",
                    severity=ERROR,
                ))
            elif policy.mode == CoercionMode.PERMISSIVE:
                errors.append(ValidationError(
                    field=field_name,
                    error_type=UNKNOWN_FIELD,
                    message=f"Unknown field '{field_name}' not in schema",
                    received=type(value).__name__,
                    suggestion=f"Consider adding '{field_name}' to the schema",
                    severity=WARNING,
                ))
                if policy.strip_unknown:
                    del result_payload[field_name]
            elif policy.mode == CoercionMode.REPORT_ONLY:
                errors.append(ValidationError(
                    field=field_name,
                    error_type=UNKNOWN_FIELD,
                    message=f"Unknown field '{field_name}' (report only)",
                    received=type(value).__name__,
                    severity=WARNING,
                ))
            continue

        if value is None and not field_spec.required:
            continue  # optional field, None is fine

        if value is None and field_spec.required:
            continue  # already caught in required check above

        # Type check
        expected_type = field_spec.field_type
        type_ok = _TYPE_CHECKS.get(expected_type, lambda v: True)(value)

        if not type_ok:
            # Try coercion in permissive mode
            if policy.mode == CoercionMode.PERMISSIVE:
                coerce_ok, coerced_val, rule = try_coerce(value, expected_type)
                if coerce_ok:
                    coercions.append(CoercionRecord(
                        field=field_name,
                        from_type=_classify_type(value),
                        to_type=expected_type,
                        from_value=value,
                        to_value=coerced_val,
                        rule=rule,
                    ))
                    result_payload[field_name] = coerced_val
                    value = coerced_val  # use coerced value for constraint checks
                else:
                    errors.append(ValidationError(
                        field=field_name,
                        error_type=WRONG_TYPE,
                        message=f"Expected {expected_type}, got {_classify_type(value)}",
                        expected=expected_type,
                        received=_classify_type(value),
                        suggestion=f"Provide '{field_name}' as {expected_type}",
                    ))
                    continue
            else:
                severity = ERROR if policy.mode == CoercionMode.STRICT else WARNING
                errors.append(ValidationError(
                    field=field_name,
                    error_type=WRONG_TYPE,
                    message=f"Expected {expected_type}, got {_classify_type(value)}",
                    expected=expected_type,
                    received=_classify_type(value),
                    suggestion=f"Provide '{field_name}' as {expected_type}",
                    severity=severity,
                ))
                continue

        # Enum check
        if expected_type == "enum" and field_spec.enum_values:
            if value not in field_spec.enum_values:
                errors.append(ValidationError(
                    field=field_name,
                    error_type=INVALID_ENUM,
                    message=f"'{value}' is not a valid value for '{field_name}'",
                    expected=field_spec.enum_values,
                    received=value,
                    suggestion=f"Set '{field_name}' to one of: {', '.join(field_spec.enum_values)}",
                ))

        # Constraint checks
        constraints = field_spec.constraints
        if constraints:
            _check_constraints(field_name, value, constraints, errors)

    # Determine outcome
    has_errors = any(e.severity == ERROR for e in errors)
    has_warnings = any(e.severity == WARNING for e in errors)

    if policy.mode == CoercionMode.REPORT_ONLY:
        outcome = "report_only_warning" if errors else "passed"
        valid = True  # report_only never blocks
    elif coercions and not has_errors:
        outcome = "coerced"
        valid = True
    elif has_errors:
        outcome = "failed"
        valid = False
    else:
        outcome = "passed"
        valid = True

    return ValidationResult(
        valid=valid,
        errors=errors,
        coercions=coercions,
        payload=result_payload,
        schema_id=schema.schema_id,
        schema_version=schema.version,
        outcome=outcome,
    )


def validate_boundary(
    boundary_id: str,
    payload: Dict[str, Any],
    registry: SchemaRegistry,
    boundary_point=None,
    audit_logger=None,
    drift_detector=None,
) -> ValidationResult:
    """Full boundary validation with registry lookup, version checking,
    coercion, drift observation, and audit logging.

    boundary_point: a BoundaryPoint from boundaries_v1_0 (if None, uses defaults).
    """
    from ironframe.io_schema.coercion_v1_0 import CoercionPolicy, CoercionMode

    # Extract boundary metadata (or defaults)
    if boundary_point:
        schema_id = boundary_point.schema_id
        schema_version = boundary_point.schema_version
        governed = boundary_point.governed
        blocking = boundary_point.blocking
        allow_minor = boundary_point.allow_minor_version_compat
        audit_required = boundary_point.audit_event_required
        drift_enabled = boundary_point.drift_observation_enabled

        # Build policy from boundary metadata
        mode_str = boundary_point.coercion_policy
        mode = CoercionMode(mode_str) if mode_str in [m.value for m in CoercionMode] else CoercionMode.STRICT
        policy = CoercionPolicy(
            mode=mode,
            allow_unknown=boundary_point.allow_unknown,
        )
    else:
        schema_id = boundary_id
        schema_version = "latest"
        governed = True
        blocking = True
        allow_minor = False
        audit_required = True
        drift_enabled = True
        policy = CoercionPolicy.strict()

    # Version compatibility check
    if schema_version != "latest":
        compat, actual_ver, reason = registry.check_version_compatible(
            schema_id, schema_version, allow_minor_compat=allow_minor
        )
        if not compat:
            is_major = reason == "major_version_mismatch"
            result = ValidationResult(
                valid=False,
                errors=[ValidationError(
                    field="",
                    error_type=VERSION_MISMATCH,
                    message=f"Schema version mismatch: requested {schema_version}, {reason}",
                    expected=schema_version,
                    received=reason,
                    suggestion="Update boundary to use the available schema version",
                    severity=ERROR,
                )],
                boundary_id=boundary_id,
                schema_id=schema_id,
                schema_version=schema_version,
                outcome="failed",
                blocking=blocking,
            )
            _log_validation(result, audit_logger, audit_required)
            return result
        schema_version = actual_ver

    # Schema lookup
    schema = registry.get(schema_id, schema_version)
    if schema is None:
        if governed:
            result = ValidationResult(
                valid=False,
                errors=[ValidationError(
                    field="",
                    error_type=SCHEMA_MISSING,
                    message=f"No schema found for governed boundary '{boundary_id}' (schema_id='{schema_id}')",
                    suggestion="Register a schema for this boundary before using it",
                    severity=ERROR,
                )],
                boundary_id=boundary_id,
                schema_id=schema_id,
                outcome="schema_missing",
                blocking=blocking,
            )
        else:
            # Non-governed: warn but allow, emit drift
            result = ValidationResult(
                valid=True,
                errors=[ValidationError(
                    field="",
                    error_type=SCHEMA_MISSING,
                    message=f"No schema found for optional boundary '{boundary_id}'",
                    suggestion="Consider registering a schema",
                    severity=WARNING,
                )],
                boundary_id=boundary_id,
                schema_id=schema_id,
                outcome="schema_missing",
                blocking=False,
            )
        _log_validation(result, audit_logger, audit_required)
        return result

    # Run validation
    result = validate_payload(payload, schema, policy)
    result.boundary_id = boundary_id
    result.blocking = blocking if not result.valid else False

    # Drift observation
    if drift_enabled and drift_detector:
        drift_detector.observe(schema_id, payload)

    # Audit logging
    _log_validation(result, audit_logger, audit_required)

    return result


def _check_constraints(field_name: str, value: Any, constraints: Dict[str, Any], errors: List[ValidationError]) -> None:
    """Check value against field constraints."""
    if "min" in constraints and isinstance(value, (int, float)):
        if value < constraints["min"]:
            errors.append(ValidationError(
                field=field_name,
                error_type=OUT_OF_RANGE,
                message=f"Value {value} is below minimum {constraints['min']}",
                expected=f">= {constraints['min']}",
                received=value,
                suggestion=f"Provide a value >= {constraints['min']}",
            ))

    if "max" in constraints and isinstance(value, (int, float)):
        if value > constraints["max"]:
            errors.append(ValidationError(
                field=field_name,
                error_type=OUT_OF_RANGE,
                message=f"Value {value} is above maximum {constraints['max']}",
                expected=f"<= {constraints['max']}",
                received=value,
                suggestion=f"Provide a value <= {constraints['max']}",
            ))

    if "min_length" in constraints and isinstance(value, (str, list)):
        if len(value) < constraints["min_length"]:
            errors.append(ValidationError(
                field=field_name,
                error_type=CONSTRAINT_VIOLATED,
                message=f"Length {len(value)} is below minimum {constraints['min_length']}",
                expected=f"length >= {constraints['min_length']}",
                received=len(value),
                suggestion=f"Provide at least {constraints['min_length']} items/characters",
            ))

    if "max_length" in constraints and isinstance(value, (str, list)):
        if len(value) > constraints["max_length"]:
            errors.append(ValidationError(
                field=field_name,
                error_type=CONSTRAINT_VIOLATED,
                message=f"Length {len(value)} exceeds maximum {constraints['max_length']}",
                expected=f"length <= {constraints['max_length']}",
                received=len(value),
                suggestion=f"Provide at most {constraints['max_length']} items/characters",
            ))

    if "pattern" in constraints and isinstance(value, str):
        if not re.match(constraints["pattern"], value):
            errors.append(ValidationError(
                field=field_name,
                error_type=CONSTRAINT_VIOLATED,
                message=f"Value does not match pattern '{constraints['pattern']}'",
                expected=f"match pattern: {constraints['pattern']}",
                received=value,
                suggestion=f"Provide a value matching the pattern: {constraints['pattern']}",
            ))


def _log_validation(result: ValidationResult, audit_logger, audit_required: bool) -> None:
    """Log validation event to audit if logger is available and required."""
    if not audit_logger or not audit_required:
        return
    try:
        audit_logger.log_event(
            event_type="schema_validation",
            component="io_schema.validator",
            details={
                "boundary_id": result.boundary_id,
                "schema_id": result.schema_id,
                "schema_version": result.schema_version,
                "outcome": result.outcome,
                "error_count": len(result.errors),
                "coercion_count": len(result.coercions),
                "blocking": result.blocking,
            },
        )
    except Exception:
        pass  # audit logging should not crash validation
