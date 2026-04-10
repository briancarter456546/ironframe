"""Component 16: I/O Schema Enforcement -- strict typed contracts for all boundaries."""

from ironframe.io_schema.errors_v1_0 import ValidationError, ValidationResult
from ironframe.io_schema.coercion_v1_0 import CoercionPolicy, CoercionMode, CoercionRecord
from ironframe.io_schema.registry_v1_0 import SchemaRegistry, SchemaDefinition, FieldSpec
from ironframe.io_schema.validator_v1_0 import validate_payload, validate_boundary
from ironframe.io_schema.boundaries_v1_0 import BoundaryPoint, get_boundary, list_boundaries
from ironframe.io_schema.drift_v1_0 import DriftDetector, DriftSignal
