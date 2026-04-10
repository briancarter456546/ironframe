# ============================================================================
# ironframe/io_schema/registry_v1_0.py - v1.0
# Last updated: 2026-04-05
# ============================================================================
# Component 16a: Schema Registry
#
# Catalog of all declared I/O schemas. Versioned. Loaded from JSON files
# in ironframe/schemas/. Follows SkillRegistry pattern (scan, load, get).
#
# Schemas are canonical-class documents per the ontology — human-approved,
# version-controlled. Unversioned schema references are drift events.
# ============================================================================

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class FieldSpec:
    """Specification for a single field within a schema."""
    name: str
    field_type: str          # string, int, float, bool, list, dict, enum, any
    required: bool = False
    default: Any = None
    description: str = ""
    enum_values: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)  # min, max, min_length, pattern, etc.
    items_type: str = ""     # for list: type of list elements

    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> "FieldSpec":
        return cls(
            name=name,
            field_type=data.get("type", "any"),
            required=data.get("required", False),
            default=data.get("default"),
            description=data.get("description", ""),
            enum_values=data.get("enum_values", []),
            constraints=data.get("constraints", {}),
            items_type=data.get("items_type", ""),
        )


@dataclass
class SchemaDefinition:
    """A single versioned schema for a boundary point."""
    schema_id: str           # e.g., "mal.complete.output"
    version: str             # e.g., "1.0"
    description: str = ""
    fields: Dict[str, FieldSpec] = field(default_factory=dict)
    required: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)  # the full JSON dict

    @property
    def major_version(self) -> int:
        try:
            return int(self.version.split(".")[0])
        except (ValueError, IndexError):
            return 0

    @property
    def minor_version(self) -> int:
        try:
            return int(self.version.split(".")[1])
        except (ValueError, IndexError):
            return 0

    def field_names(self) -> List[str]:
        return list(self.fields.keys())

    def get_field(self, name: str) -> Optional[FieldSpec]:
        return self.fields.get(name)

    def has_any_fields(self) -> bool:
        """Check if schema contains any 'any' typed fields (weakly typed)."""
        return any(f.field_type == "any" for f in self.fields.values())

    def any_field_names(self) -> List[str]:
        """Return names of fields typed as 'any' (for drift flagging)."""
        return [f.name for f in self.fields.values() if f.field_type == "any"]

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "SchemaDefinition":
        fields = {}
        for fname, fdata in data.get("fields", {}).items():
            fields[fname] = FieldSpec.from_dict(fname, fdata)

        return cls(
            schema_id=data.get("schema_id", ""),
            version=data.get("version", "1.0"),
            description=data.get("description", ""),
            fields=fields,
            required=data.get("required", []),
            raw=data,
        )

    def to_json(self) -> Dict[str, Any]:
        return self.raw


class SchemaRegistry:
    """Catalog of all declared I/O schemas, versioned.

    Loads from JSON files in a schemas directory.
    Keyed by (schema_id, version). "latest" resolves to highest version.
    """

    def __init__(self, schema_dir: str = "ironframe/schemas"):
        self._dir = Path(schema_dir)
        self._schemas: Dict[str, Dict[str, SchemaDefinition]] = {}  # schema_id -> {version -> def}

    def load_all(self) -> int:
        """Scan schema directory and load all JSON files. Returns count loaded."""
        self._schemas.clear()
        if not self._dir.exists():
            return 0

        count = 0
        for json_file in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                schema = SchemaDefinition.from_json(data)
                if schema.schema_id:
                    self.register(schema)
                    count += 1
            except (json.JSONDecodeError, KeyError):
                continue
        return count

    def register(self, schema: SchemaDefinition) -> None:
        """Register a schema definition."""
        if schema.schema_id not in self._schemas:
            self._schemas[schema.schema_id] = {}
        self._schemas[schema.schema_id][schema.version] = schema

    def get(self, schema_id: str, version: str = "latest") -> Optional[SchemaDefinition]:
        """Get a schema by ID and version. 'latest' returns highest version."""
        versions = self._schemas.get(schema_id, {})
        if not versions:
            return None

        if version == "latest":
            latest_key = max(versions.keys(), key=lambda v: _version_tuple(v))
            return versions[latest_key]

        return versions.get(version)

    def has(self, schema_id: str, version: str = "latest") -> bool:
        """Check if a schema exists."""
        return self.get(schema_id, version) is not None

    def list_schemas(self) -> List[str]:
        """List all schema IDs."""
        return sorted(self._schemas.keys())

    def versions(self, schema_id: str) -> List[str]:
        """List all versions of a schema."""
        return sorted(self._schemas.get(schema_id, {}).keys(), key=lambda v: _version_tuple(v))

    def check_version_compatible(
        self,
        schema_id: str,
        requested_version: str,
        allow_minor_compat: bool = False,
    ) -> tuple:
        """Check if a requested version is compatible with what's registered.

        Returns (compatible: bool, actual_version: str, reason: str).
        """
        schema = self.get(schema_id, requested_version)
        if schema:
            return True, requested_version, "exact_match"

        if not allow_minor_compat:
            return False, "", "exact_version_not_found"

        # Try minor version compatibility
        available = self._schemas.get(schema_id, {})
        for avail_version, avail_schema in available.items():
            req_major = _version_tuple(requested_version)[0]
            avail_major = avail_schema.major_version
            if req_major == avail_major:
                return True, avail_version, "minor_version_compat"

        return False, "", "major_version_mismatch"

    def summary(self) -> Dict[str, Any]:
        """Return registry summary."""
        total = sum(len(v) for v in self._schemas.values())
        any_typed = []
        for sid, versions in self._schemas.items():
            for ver, schema in versions.items():
                if schema.has_any_fields():
                    any_typed.append(f"{sid}@{ver}: {schema.any_field_names()}")
        return {
            "schema_count": len(self._schemas),
            "version_count": total,
            "schema_ids": self.list_schemas(),
            "weakly_typed_schemas": any_typed,
        }


def _version_tuple(v: str) -> tuple:
    """Convert version string to tuple for comparison."""
    try:
        parts = v.split(".")
        return tuple(int(p) for p in parts)
    except (ValueError, AttributeError):
        return (0, 0)
