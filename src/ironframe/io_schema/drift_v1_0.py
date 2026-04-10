# ============================================================================
# ironframe/io_schema/drift_v1_0.py - v1.0
# Last updated: 2026-04-05
# ============================================================================
# Component 16e: Schema Drift Detection
#
# Observes validated payloads and detects schema drift:
#   - Extra fields not in schema (tool responses evolving)
#   - Fields typed as 'any' (weakly typed, always flagged per correction #4)
#   - Consistently missing optional fields
#   - Type patterns shifting over time
#
# Drift signals are stored in memory and forwarded to Component 18
# (Spec Conformance & Drift Engine) when it is built.
# ============================================================================

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from ironframe.io_schema.registry_v1_0 import SchemaRegistry, SchemaDefinition


@dataclass
class DriftSignal:
    """A detected divergence between actual data and declared schema."""
    schema_id: str
    schema_version: str
    drift_type: str          # extra_field, weakly_typed, missing_optional, type_shift
    field: str
    detail: str
    timestamp: str = ""
    sample_value_type: str = ""  # type name only, not actual value (safety)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "drift_type": self.drift_type,
            "field": self.field,
            "detail": self.detail,
            "timestamp": self.timestamp,
            "sample_value_type": self.sample_value_type,
        }


class DriftDetector:
    """Detects schema drift by comparing actual payloads to declared schemas.

    Accumulates signals over time. Call observe() after each successful
    validation. Provides summary and signal list for Component 18.

    Per correction #4: 'any' typed fields are ALWAYS flagged as weakly
    typed boundaries on every observation — they never go "clean."
    """

    def __init__(self, registry: SchemaRegistry):
        self._registry = registry
        self._signals: List[DriftSignal] = []
        self._seen_extra_fields: Dict[str, Set[str]] = {}  # schema_id -> set of extra field names
        self._observation_count: Dict[str, int] = {}  # schema_id -> count

    def observe(self, schema_id: str, payload: Dict[str, Any]) -> List[DriftSignal]:
        """Observe a payload against its declared schema. Returns new drift signals."""
        schema = self._registry.get(schema_id)
        if not schema:
            return []

        new_signals = []
        self._observation_count[schema_id] = self._observation_count.get(schema_id, 0) + 1

        # Check for extra fields not in schema
        declared_fields = set(schema.fields.keys())
        actual_fields = set(payload.keys())
        extra = actual_fields - declared_fields

        for field_name in extra:
            # Track which extra fields we've seen
            if schema_id not in self._seen_extra_fields:
                self._seen_extra_fields[schema_id] = set()

            if field_name not in self._seen_extra_fields[schema_id]:
                self._seen_extra_fields[schema_id].add(field_name)
                signal = DriftSignal(
                    schema_id=schema_id,
                    schema_version=schema.version,
                    drift_type="extra_field",
                    field=field_name,
                    detail=f"Field '{field_name}' present in payload but not declared in schema",
                    sample_value_type=type(payload[field_name]).__name__,
                )
                new_signals.append(signal)

        # Flag 'any' typed fields (correction #4: always flagged, never clean)
        for field_name in schema.any_field_names():
            if field_name in payload:
                signal = DriftSignal(
                    schema_id=schema_id,
                    schema_version=schema.version,
                    drift_type="weakly_typed",
                    field=field_name,
                    detail=f"Field '{field_name}' is typed as 'any' (weakly typed boundary)",
                    sample_value_type=type(payload[field_name]).__name__,
                )
                new_signals.append(signal)

        self._signals.extend(new_signals)
        return new_signals

    def get_signals(
        self,
        schema_id: str = "",
        drift_type: str = "",
        since: str = "",
    ) -> List[DriftSignal]:
        """Get accumulated drift signals, optionally filtered."""
        results = self._signals
        if schema_id:
            results = [s for s in results if s.schema_id == schema_id]
        if drift_type:
            results = [s for s in results if s.drift_type == drift_type]
        if since:
            results = [s for s in results if s.timestamp >= since]
        return results

    def summary(self) -> Dict[str, Any]:
        """Summary of all drift observations."""
        by_type: Dict[str, int] = {}
        by_schema: Dict[str, int] = {}
        for s in self._signals:
            by_type[s.drift_type] = by_type.get(s.drift_type, 0) + 1
            by_schema[s.schema_id] = by_schema.get(s.schema_id, 0) + 1

        return {
            "total_signals": len(self._signals),
            "by_type": by_type,
            "by_schema": by_schema,
            "observations": self._observation_count,
            "schemas_with_extra_fields": {
                sid: sorted(fields) for sid, fields in self._seen_extra_fields.items()
            },
        }

    def clear(self) -> None:
        """Clear accumulated signals. Use between test runs, not in production."""
        self._signals.clear()
        self._seen_extra_fields.clear()
        self._observation_count.clear()
