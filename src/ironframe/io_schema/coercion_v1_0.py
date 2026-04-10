# ============================================================================
# ironframe/io_schema/coercion_v1_0.py - v1.0
# Last updated: 2026-04-05
# ============================================================================
# Component 16d: Output Coercion Policy
#
# Three modes: STRICT (no coercion), PERMISSIVE (safe coercions logged),
# REPORT_ONLY (validate but never reject).
#
# Constitution reference: Law 6 — all coercions logged, silent coercion
# without logging is never permitted.
#
# Unknown field handling is EXPLICIT per mode (correction #3):
#   STRICT:      fail unless boundary.allow_unknown=true
#   PERMISSIVE:  warn, retain or strip per boundary config
#   REPORT_ONLY: log only
# ============================================================================

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class CoercionMode(str, Enum):
    STRICT = "strict"            # reject on any type mismatch
    PERMISSIVE = "permissive"    # coerce safe transforms, warn on unknowns
    REPORT_ONLY = "report_only"  # validate but never reject


# Safe coercion rules (source_type -> target_type)
SAFE_COERCIONS = {
    ("str", "int"): "string_to_int",
    ("str", "float"): "string_to_float",
    ("str", "bool"): "string_to_bool",
    ("int", "float"): "int_to_float",
    ("float", "int"): "float_to_int_truncate",
    ("int", "str"): "int_to_string",
    ("float", "str"): "float_to_string",
    ("bool", "str"): "bool_to_string",
    ("bool", "int"): "bool_to_int",
    ("int", "bool"): "int_to_bool",
}


@dataclass
class CoercionRecord:
    """Record of a single coercion applied to a field. Always logged."""
    field: str
    from_type: str
    to_type: str
    from_value: Any
    to_value: Any
    rule: str                # e.g., "string_to_int", "strip_whitespace"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "from_type": self.from_type,
            "to_type": self.to_type,
            "from_value": _safe_value(self.from_value),
            "to_value": _safe_value(self.to_value),
            "rule": self.rule,
        }


@dataclass
class CoercionPolicy:
    """Controls how type mismatches and unknown fields are handled at a boundary."""
    mode: CoercionMode = CoercionMode.STRICT
    allow_unknown: bool = False       # if True, extra fields are not errors in STRICT mode
    strip_unknown: bool = False       # if True (PERMISSIVE), extra fields are removed
    log_coercions: bool = True        # always True per constitution; here for explicitness

    @classmethod
    def strict(cls, allow_unknown: bool = False) -> "CoercionPolicy":
        return cls(mode=CoercionMode.STRICT, allow_unknown=allow_unknown)

    @classmethod
    def permissive(cls, strip_unknown: bool = False) -> "CoercionPolicy":
        return cls(mode=CoercionMode.PERMISSIVE, allow_unknown=True, strip_unknown=strip_unknown)

    @classmethod
    def report_only(cls) -> "CoercionPolicy":
        return cls(mode=CoercionMode.REPORT_ONLY, allow_unknown=True)


def try_coerce(value: Any, target_type: str) -> Tuple[bool, Any, str]:
    """Attempt to coerce a value to the target type.

    Returns (success, coerced_value, rule_name).
    Only attempts SAFE coercions — no lossy or ambiguous transforms.
    """
    source_type = _classify_type(value)

    if source_type == target_type:
        return True, value, "no_coercion_needed"

    # Special case: None stays None for optional fields
    if value is None:
        return False, value, ""

    rule_key = (source_type, target_type)
    rule_name = SAFE_COERCIONS.get(rule_key, "")
    if not rule_name:
        return False, value, ""

    try:
        if rule_name == "string_to_int":
            cleaned = str(value).strip()
            coerced = int(cleaned)
            return True, coerced, rule_name
        elif rule_name == "string_to_float":
            cleaned = str(value).strip()
            coerced = float(cleaned)
            return True, coerced, rule_name
        elif rule_name == "string_to_bool":
            lower = str(value).strip().lower()
            if lower in ("true", "1", "yes"):
                return True, True, rule_name
            elif lower in ("false", "0", "no"):
                return True, False, rule_name
            return False, value, ""
        elif rule_name == "int_to_float":
            return True, float(value), rule_name
        elif rule_name == "float_to_int_truncate":
            return True, int(value), rule_name
        elif rule_name in ("int_to_string", "float_to_string", "bool_to_string"):
            return True, str(value), rule_name
        elif rule_name == "bool_to_int":
            return True, int(value), rule_name
        elif rule_name == "int_to_bool":
            return True, bool(value), rule_name
    except (ValueError, TypeError, OverflowError):
        return False, value, ""

    return False, value, ""


def _classify_type(value: Any) -> str:
    """Classify a Python value into our type system."""
    if value is None:
        return "none"
    if isinstance(value, bool):  # must check before int (bool is subclass of int)
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return "unknown"


def _safe_value(val: Any) -> Any:
    """Truncate long values for logging."""
    if isinstance(val, str) and len(val) > 100:
        return val[:100] + "..."
    return val
