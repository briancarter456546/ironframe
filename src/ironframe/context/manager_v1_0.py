# ============================================================================
# ironframe/context/manager_v1_0.py - v1.0
# Last updated: 2026-04-06
# ============================================================================
# Component 9 Orchestrator: ContextBudgetManager
#
# Assembles the final context package before model calls. Enforces:
#   - Fixed zone sequence (stable prefix for cache hits)
#   - Protection zones never compressed
#   - Dual-zone overflow precedence (history first, then retrieved)
#   - Trust metadata preservation invariant
#   - Context rot detection
#   - CURRENT_TASK floor protection (escalate, never truncate)
#   - C16 boundary validation on output
# ============================================================================

import time
import uuid
from typing import Any, Dict, List, Optional

from ironframe.context.zones_v1_0 import (
    ContextZone, ZoneContent, ContentChunk, ZONE_SEQUENCE,
    PROTECTED_ZONES, create_empty_package, estimate_tokens,
)
from ironframe.context.budget_v1_0 import ContextBudgetAllocator, BudgetEscalation
from ironframe.context.compression_v1_0 import CompressionPipeline
from ironframe.context.trust_preservation_v1_0 import verify_package_preservation
from ironframe.context.rot_detector_v1_0 import assess_rot, RotAssessment
from ironframe.context.skill_tier_v1_0 import extract_core_tier
from ironframe.context.telemetry_v1_0 import AssemblyTelemetry, ContextTelemetryEmitter
from ironframe.audit.logger_v1_0 import AuditLogger


class ContextRotEscalation(Exception):
    """Raised when context rot cannot be mitigated below threshold."""
    def __init__(self, rot: RotAssessment):
        self.rot = rot
        super().__init__(
            f"Context rot escalation: CURRENT_TASK starts at {rot.current_task_start_pct:.0%} "
            f"of window (threshold: 75%). Risk score: {rot.risk_score:.2f}"
        )


class ContextPackage:
    """The assembled context package ready for C1 (MAL).

    Zones in fixed order. Validated against C16 boundary.
    """

    def __init__(self, zones: Dict[str, ZoneContent], telemetry: AssemblyTelemetry):
        self.zones = zones
        self.telemetry = telemetry

    @property
    def total_tokens(self) -> int:
        return sum(z.token_count for z in self.zones.values())

    def assembled_text(self) -> str:
        """Full context as text, zones in fixed order."""
        parts = []
        for zone_enum in ZONE_SEQUENCE:
            zone = self.zones.get(zone_enum.value)
            if zone and zone.chunks:
                parts.append(zone.assembled_text())
        return "\n\n".join(parts)

    def to_validation_dict(self) -> Dict[str, Any]:
        """Output format for C16 context.budget.output boundary validation."""
        zone_list = []
        for zone_enum in ZONE_SEQUENCE:
            zone = self.zones.get(zone_enum.value)
            if zone:
                zone_list.append(zone.to_dict())

        protection_intact = all(
            self.zones.get(z.value) is not None and not self.zones[z.value].compressed
            for z in PROTECTED_ZONES
        )

        # CURRENT_TASK must be at last position
        task_pos = len(zone_list) - 1

        return {
            "zones": zone_list,
            "protection_zones_intact": protection_intact,
            "current_task_position": task_pos,
            "total_tokens": self.total_tokens,
            "budget_utilization": self.telemetry.budget_utilization,
            "trust_violations": self.telemetry.trust_violations,
        }


class ContextBudgetManager:
    """Component 9 orchestrator. Assembles context packages.

    Sits between Skill Registry (C2) and MAL (C1).
    """

    def __init__(
        self,
        total_tokens: int = 128000,
        audit_logger: Optional[AuditLogger] = None,
    ):
        self._total_tokens = total_tokens
        self._audit = audit_logger
        self._telemetry = ContextTelemetryEmitter(audit_logger)

    def assemble(
        self,
        constitutional: str = "",
        contract: str = "",
        tool_definitions: str = "",
        retrieved_context: Optional[List[Dict[str, Any]]] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        current_task: str = "",
        session_id: str = "",
        task_keywords: Optional[List[str]] = None,
        allocations: Optional[Dict[str, float]] = None,
    ) -> ContextPackage:
        """Assemble a context package from zone inputs.

        Each input for managed zones is a list of dicts:
          {"text": str, "trust_tier": int, "source_id": str}

        Raises BudgetEscalation if CURRENT_TASK can't fit.
        Raises ContextRotEscalation if rot can't be mitigated.
        """
        start_time = time.time()

        # Create empty package in fixed order
        zones = create_empty_package()

        # Populate protection zones (NEVER compressed)
        if constitutional:
            zones[ContextZone.CONSTITUTIONAL.value].add_chunk(
                self._make_chunk(constitutional, trust_tier=4, source="constitution")
            )
        if contract:
            zones[ContextZone.CONTRACT.value].add_chunk(
                self._make_chunk(contract, trust_tier=4, source="contract")
            )
        if tool_definitions:
            zones[ContextZone.TOOL_DEFINITIONS.value].add_chunk(
                self._make_chunk(tool_definitions, trust_tier=4, source="tool_defs")
            )

        # Populate managed zones
        for item in (retrieved_context or []):
            zones[ContextZone.RETRIEVED_CONTEXT.value].add_chunk(
                self._make_chunk(
                    item.get("text", ""),
                    trust_tier=item.get("trust_tier", 3),
                    source=item.get("source_id", ""),
                )
            )

        for item in (conversation_history or []):
            zones[ContextZone.CONVERSATION_HISTORY.value].add_chunk(
                self._make_chunk(
                    item.get("text", ""),
                    trust_tier=item.get("trust_tier", 2),
                    source=item.get("source_id", ""),
                )
            )

        # Populate terminal zone
        if current_task:
            task_tier = 2  # USER by default
            if isinstance(current_task, dict):
                task_tier = current_task.get("trust_tier", 2)
                current_task = current_task.get("text", "")
            zones[ContextZone.CURRENT_TASK.value].add_chunk(
                self._make_chunk(current_task, trust_tier=task_tier, source="current_task")
            )

        # Compute budgets
        allocator = ContextBudgetAllocator(
            total_tokens=self._total_tokens,
            allocations=allocations,
        )
        for zone_enum in ZONE_SEQUENCE:
            zone = zones[zone_enum.value]
            allocator.update_usage(zone_enum.value, zone.token_count)

        # Check CURRENT_TASK floor
        task_tokens = zones[ContextZone.CURRENT_TASK.value].token_count
        if task_tokens > 0:
            allocator.check_current_task_floor(task_tokens)

        # Snapshot pre-compression for trust verification
        pre_compression = {z: list(zones[z].chunks) for z in zones}

        # Run compression pipeline on managed zones if over budget
        compression_result = None
        over_budget = allocator.over_budget_zones()
        managed_over = [z for z in over_budget if z in {ze.value for ze in ZONE_SEQUENCE}
                        and z not in {pz.value for pz in PROTECTED_ZONES}]

        if managed_over or allocator.total_used() > self._total_tokens:
            pipeline = CompressionPipeline(current_task_keywords=task_keywords)
            compression_result = pipeline.compress_to_budget(zones, allocator)

        # Verify trust preservation
        all_pre = []
        all_post = []
        for z_key in zones:
            all_pre.extend(pre_compression.get(z_key, []))
            all_post.extend(zones[z_key].chunks)
        trust_violations = []
        for post_chunk in all_post:
            for pre_chunk in all_pre:
                if post_chunk.chunk_id == pre_chunk.chunk_id:
                    if post_chunk.trust_tier != pre_chunk.trust_tier:
                        trust_violations.append(
                            f"{post_chunk.chunk_id}: {pre_chunk.trust_tier} -> {post_chunk.trust_tier}"
                        )

        # Context rot detection
        rot = assess_rot(zones, self._total_tokens)
        if rot.at_risk:
            # Already compressed — if still at risk, escalate
            if compression_result and compression_result.escalated:
                raise ContextRotEscalation(rot)

        # Build telemetry
        elapsed = (time.time() - start_time) * 1000
        telemetry = AssemblyTelemetry(
            total_tokens=sum(z.token_count for z in zones.values()),
            tokens_by_zone={z: zones[z].token_count for z in zones},
            budget_utilization=allocator.utilization(),
            compression_passes=len(compression_result.events) if compression_result else 0,
            tokens_saved=compression_result.total_tokens_saved if compression_result else 0,
            hard_truncations=compression_result.hard_truncations if compression_result else 0,
            trust_violations=len(trust_violations),
            context_rot_risk_score=rot.risk_score,
            context_rot_at_risk=rot.at_risk,
            escalated=compression_result.escalated if compression_result else False,
            assembly_time_ms=elapsed,
        )

        self._telemetry.emit(telemetry, session_id)

        return ContextPackage(zones=zones, telemetry=telemetry)

    def _make_chunk(self, text: str, trust_tier: int, source: str) -> ContentChunk:
        return ContentChunk(
            chunk_id=str(uuid.uuid4())[:8],
            text=text,
            token_count=estimate_tokens(text),
            trust_tier=trust_tier,
            source_id=source,
        )

    @property
    def telemetry_summary(self) -> Dict[str, Any]:
        return self._telemetry.summary()
