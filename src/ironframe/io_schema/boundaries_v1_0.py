# ============================================================================
# ironframe/io_schema/boundaries_v1_0.py - v1.0
# Last updated: 2026-04-05
# ============================================================================
# Component 16b: Boundary Point Catalog
#
# Declares all typed boundaries in the system with rich metadata:
# schema_id, version, coercion policy, blocking, governed, etc.
# (correction #2: full operational metadata, not just schema_id)
# ============================================================================

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class BoundaryPoint:
    """Declaration of a single typed boundary in the system.

    Rich metadata per correction #2: each boundary declares its own
    coercion policy, blocking behavior, governance level, and versioning.
    """
    boundary_id: str                      # "mal.complete.output"
    component: str                        # "mal.client"
    direction: str                        # "input" or "output"
    schema_id: str                        # references SchemaRegistry
    schema_version: str = "1.0"           # pinned version or "latest"
    description: str = ""
    coercion_policy: str = "strict"       # "strict", "permissive", "report_only"
    blocking: bool = True                 # validation failure halts pipeline
    governed: bool = True                 # missing schema = hard fail
    allow_unknown: bool = False           # extra fields not errors in strict
    allow_minor_version_compat: bool = False
    audit_event_required: bool = True     # every validation logged to audit
    drift_observation_enabled: bool = True


# ---- Boundary Catalog ----
# All declared boundary points for existing components 1-8

BOUNDARY_CATALOG: Dict[str, BoundaryPoint] = {

    # --- Component 1: MAL ---
    "mal.complete.output": BoundaryPoint(
        boundary_id="mal.complete.output",
        component="mal.client",
        direction="output",
        schema_id="mal.complete.output",
        description="Output from IronFrameClient.complete()",
        coercion_policy="strict",
        blocking=True,
        governed=True,
        allow_unknown=True,  # adapters may add extra fields
    ),
    "mal.stream.chunk": BoundaryPoint(
        boundary_id="mal.stream.chunk",
        component="mal.client",
        direction="output",
        schema_id="mal.stream.chunk",
        description="Streaming chunk from IronFrameClient.stream()",
        coercion_policy="permissive",
        blocking=False,  # don't block individual chunks
        governed=True,
        allow_unknown=True,
        audit_event_required=False,  # too noisy per-chunk
        drift_observation_enabled=False,
    ),
    "mal.stream.final": BoundaryPoint(
        boundary_id="mal.stream.final",
        component="mal.client",
        direction="output",
        schema_id="mal.stream.final",
        description="Final summary from IronFrameClient.stream()",
        coercion_policy="strict",
        blocking=True,
        governed=True,
        allow_unknown=True,
    ),

    # --- Component 5: SAE ---
    "sae.judge.evaluate.output": BoundaryPoint(
        boundary_id="sae.judge.evaluate.output",
        component="sae.judge",
        direction="output",
        schema_id="sae.judge.evaluate.output",
        description="Judge verdict from Judge.evaluate()",
        coercion_policy="permissive",  # LLM output needs coercion tolerance
        blocking=False,  # judge already has graceful degradation
        governed=True,
        allow_unknown=True,  # LLM may add extra fields
    ),
    "sae.cross_model.verify.output": BoundaryPoint(
        boundary_id="sae.cross_model.verify.output",
        component="sae.cross_model",
        direction="output",
        schema_id="sae.cross_model.verify.output",
        description="Cross-model verification verdict",
        coercion_policy="permissive",
        blocking=False,
        governed=True,
        allow_unknown=True,
    ),

    # --- Component 4: Hooks ---
    "hooks.result": BoundaryPoint(
        boundary_id="hooks.result",
        component="hooks.engine",
        direction="output",
        schema_id="hooks.result",
        description="HookResult from hook execution",
        coercion_policy="strict",
        blocking=False,  # hook results are already dataclass-typed
        governed=True,
        allow_unknown=False,
        drift_observation_enabled=False,  # dataclass enforces structure
    ),

    # --- Component 7: Audit ---
    "audit.event": BoundaryPoint(
        boundary_id="audit.event",
        component="audit.logger",
        direction="output",
        schema_id="audit.event",
        description="AuditEvent before write to log",
        coercion_policy="strict",
        blocking=True,  # bad audit events must not be written
        governed=True,
        allow_unknown=False,
    ),

    # --- Component 2: Skills ---
    "skills.definition": BoundaryPoint(
        boundary_id="skills.definition",
        component="skills.registry",
        direction="output",
        schema_id="skills.definition",
        description="Skill definition from registry scan",
        coercion_policy="permissive",
        blocking=False,
        governed=False,  # transitional — existing skills lack full metadata
        allow_unknown=True,
        allow_minor_version_compat=True,
    ),
}


def get_boundary(boundary_id: str) -> Optional[BoundaryPoint]:
    """Get a boundary point by ID."""
    return BOUNDARY_CATALOG.get(boundary_id)


def list_boundaries(component: str = "") -> List[BoundaryPoint]:
    """List boundary points, optionally filtered by component."""
    if component:
        return [bp for bp in BOUNDARY_CATALOG.values() if bp.component == component]
    return list(BOUNDARY_CATALOG.values())


def list_governed() -> List[str]:
    """List all governed boundary IDs."""
    return [bp.boundary_id for bp in BOUNDARY_CATALOG.values() if bp.governed]


def list_blocking() -> List[str]:
    """List all blocking boundary IDs."""
    return [bp.boundary_id for bp in BOUNDARY_CATALOG.values() if bp.blocking]
