# ============================================================================
# ironframe/conformance/rtm_v1_0.py - v1.0
# Last updated: 2026-04-08
# ============================================================================
# Component 18a: Requirements Traceability Matrix (RTM) Backbone
#
# Machine-readable RTM stored as canonical KB artifact. Each requirement
# links to implementation code, verification tests, and runtime evidence.
#
# Rules:
#   - No accepted requirement may have zero implementation_artifacts
#   - No accepted requirement may have zero verification_artifacts
#   - Violations = RTM_COVERAGE_GAP drift event
# ============================================================================

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RTMEntry:
    """A single requirement in the traceability matrix."""
    requirement_id: str
    description: str
    type: str = "functional"          # functional, nonfunctional, compliance, safety
    status: str = "accepted"          # proposed, accepted, deprecated
    source: str = "architecture"      # regulation, internal_policy, architecture
    component_ids: List[str] = field(default_factory=list)
    implementation_artifacts: List[str] = field(default_factory=list)
    verification_artifacts: List[str] = field(default_factory=list)
    compliance_refs: List[str] = field(default_factory=list)

    @property
    def has_implementation(self) -> bool:
        return len(self.implementation_artifacts) > 0

    @property
    def has_verification(self) -> bool:
        return len(self.verification_artifacts) > 0

    @property
    def is_complete(self) -> bool:
        """An accepted requirement must have both impl and verification."""
        if self.status != "accepted":
            return True  # only accepted reqs need coverage
        return self.has_implementation and self.has_verification

    def coverage_gaps(self) -> List[str]:
        """Return list of coverage gap descriptions."""
        if self.status != "accepted":
            return []
        gaps = []
        if not self.has_implementation:
            gaps.append(f"{self.requirement_id}: no implementation artifacts")
        if not self.has_verification:
            gaps.append(f"{self.requirement_id}: no verification artifacts")
        return gaps

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "description": self.description,
            "type": self.type,
            "status": self.status,
            "source": self.source,
            "component_ids": self.component_ids,
            "implementation_artifacts": self.implementation_artifacts,
            "verification_artifacts": self.verification_artifacts,
            "compliance_refs": self.compliance_refs,
            "is_complete": self.is_complete,
        }


class RTMRegistry:
    """Manages the Requirements Traceability Matrix."""

    def __init__(self):
        self._entries: Dict[str, RTMEntry] = {}

    def add(self, entry: RTMEntry) -> None:
        self._entries[entry.requirement_id] = entry

    def get(self, req_id: str) -> Optional[RTMEntry]:
        return self._entries.get(req_id)

    def list_all(self) -> List[RTMEntry]:
        return list(self._entries.values())

    def list_by_component(self, component_id: str) -> List[RTMEntry]:
        return [e for e in self._entries.values() if component_id in e.component_ids]

    def list_by_status(self, status: str) -> List[RTMEntry]:
        return [e for e in self._entries.values() if e.status == status]

    def coverage_gaps(self) -> List[str]:
        """All coverage gaps across accepted requirements."""
        gaps = []
        for entry in self._entries.values():
            gaps.extend(entry.coverage_gaps())
        return gaps

    def coverage_report(self) -> Dict[str, Dict[str, Any]]:
        """Per-requirement coverage status."""
        report = {}
        for entry in self._entries.values():
            report[entry.requirement_id] = {
                "description": entry.description,
                "status": entry.status,
                "has_implementation": entry.has_implementation,
                "has_verification": entry.has_verification,
                "is_complete": entry.is_complete,
                "component_ids": entry.component_ids,
            }
        return report

    def untested_requirements(self) -> List[str]:
        """Requirements with no verification artifacts."""
        return [e.requirement_id for e in self._entries.values()
                if e.status == "accepted" and not e.has_verification]

    def compliance_query(self, regulation_id: str = "", requirement_id: str = "") -> List[Dict[str, Any]]:
        """Query requirements by regulation or ID. Returns full evidence chain."""
        results = []
        for entry in self._entries.values():
            if requirement_id and entry.requirement_id != requirement_id:
                continue
            if regulation_id and regulation_id not in str(entry.compliance_refs):
                continue
            results.append({
                "requirement": entry.to_dict(),
                "implementation": entry.implementation_artifacts,
                "verification": entry.verification_artifacts,
                "compliance_refs": entry.compliance_refs,
            })
        return results

    def summary(self) -> Dict[str, Any]:
        total = len(self._entries)
        accepted = len(self.list_by_status("accepted"))
        complete = sum(1 for e in self._entries.values() if e.is_complete)
        return {
            "total": total,
            "accepted": accepted,
            "complete": complete,
            "coverage_gaps": len(self.coverage_gaps()),
            "untested": len(self.untested_requirements()),
        }


def seed_rtm() -> RTMRegistry:
    """Create RTM with 12 seeded requirements from 18packet.txt."""
    rtm = RTMRegistry()

    rtm.add(RTMEntry(
        requirement_id="IF-REQ-001",
        description="Iron Frame must audit every significant decision and event",
        type="nonfunctional", source="architecture",
        component_ids=["C7"],
        implementation_artifacts=[
            "ironframe/audit/logger_v1_0.py", "ironframe/audit/schema_v1_0.py",
            "ironframe/audit/stream_logger_v1_0.py",
            "ironframe/compliance/audit_requirements_v1_0.py",
            "ironframe/compliance/base_v1_0.py",
        ],
        verification_artifacts=["test_harness_v1_0:audit_logging", "ironframe/test_harness_v1_0.py"],
    ))
    rtm.add(RTMEntry(
        requirement_id="IF-REQ-002",
        description="Iron Frame must enforce least-privilege tool access",
        type="safety", source="architecture",
        component_ids=["C12", "C17"],
        implementation_artifacts=[
            "ironframe/tool_governance/governor_v1_0.py", "ironframe/agent_trust/permissions_v1_0.py",
            "ironframe/tool_governance/auth_v1_0.py",
            "ironframe/tool_governance/contract_v1_0.py",
            "ironframe/tool_governance/rate_limit_v1_0.py",
            "ironframe/tool_governance/registry_v1_0.py",
            "ironframe/tool_governance/versioning_v1_0.py",
            "ironframe/tool_governance/locks_v1_0.py",
        ],
        verification_artifacts=["c12-tool-governance-tests", "c17-permission-tests"],
    ))
    rtm.add(RTMEntry(
        requirement_id="IF-REQ-003",
        description="Iron Frame must self-audit outputs for accuracy and completeness",
        type="functional", source="architecture",
        component_ids=["C5"],
        implementation_artifacts=[
            "ironframe/sae/confidence_v1_0.py", "ironframe/sae/judge_v1_0.py",
            "ironframe/sae/tiers_v1_0.py", "ironframe/sae/cross_model_v1_0.py",
            "ironframe/mal/client_v1_0.py", "ironframe/mal/router_v1_0.py",
            "ironframe/mal/adapters/anthropic_v1_0.py",
            "ironframe/mal/adapters/perplexity_v1_0.py",
        ],
        verification_artifacts=["test_harness_v1_0:judge_verdict", "ironframe/test_harness_v1_0.py"],
    ))
    rtm.add(RTMEntry(
        requirement_id="IF-REQ-004",
        description="Multi-agent coordination must enforce structured protocol",
        type="functional", source="architecture",
        component_ids=["C14"],
        implementation_artifacts=[
            "ironframe/coordination/protocol_v1_0.py", "ironframe/coordination/messages_v1_0.py",
            "ironframe/coordination/roles_v1_0.py", "ironframe/coordination/tasks_v1_0.py",
        ],
        verification_artifacts=["c14-multi-agent-clean", "ironframe/tests/test_c14_coordination.py"],
    ))
    rtm.add(RTMEntry(
        requirement_id="IF-REQ-004A",
        description="No message may cause trust escalation",
        type="safety", source="architecture",
        component_ids=["C14", "C17"],
        implementation_artifacts=["ironframe/coordination/messages_v1_0.py"],
        verification_artifacts=["c14-multi-agent-clean", "V-C14-004"],
    ))
    rtm.add(RTMEntry(
        requirement_id="IF-REQ-004B",
        description="Shared resources must be serialized by graph priority",
        type="functional", source="architecture",
        component_ids=["C14", "C12"],
        implementation_artifacts=[
            "ironframe/coordination/resources_v1_0.py",
            "ironframe/tool_governance/locks_v1_0.py",
        ],
        verification_artifacts=["V-C14-009"],
    ))
    rtm.add(RTMEntry(
        requirement_id="IF-REQ-004C",
        description="Loop detection must trigger halt when threshold exceeded",
        type="safety", source="architecture",
        component_ids=["C14"],
        implementation_artifacts=["ironframe/coordination/loops_v1_0.py"],
        verification_artifacts=["V-C14-008"],
    ))
    rtm.add(RTMEntry(
        requirement_id="IF-REQ-004D",
        description="Handoffs must require orchestrator acknowledgment",
        type="functional", source="architecture",
        component_ids=["C14"],
        implementation_artifacts=["ironframe/coordination/handoff_v1_0.py"],
        verification_artifacts=["V-C14-007"],
    ))
    rtm.add(RTMEntry(
        requirement_id="IF-REQ-005",
        description="Iron Frame must detect and report deviation from spec",
        type="nonfunctional", source="architecture",
        component_ids=["C18"],
        implementation_artifacts=[
            "ironframe/conformance/engine_v1_0.py", "ironframe/conformance/static_checker_v1_0.py",
            "ironframe/conformance/runtime_monitor_v1_0.py",
            "ironframe/conformance/drift_reporter_v1_0.py",
            "ironframe/conformance/rtm_v1_0.py",
        ],
        verification_artifacts=[
            "c18-static-clean", "c18-trust-drift", "c18-rtm-gap",
            "ironframe/eval/scenarios/c18_scenarios.py",
            "ironframe/tests/test_c18_conformance.py",
            "ironframe/tests/test_rtm_coverage.py",
            "ironframe/tests/test_wiring.py",
        ],
    ))
    rtm.add(RTMEntry(
        requirement_id="IF-REQ-006",
        description="Context budget must be actively managed to prevent token waste",
        type="nonfunctional", source="architecture",
        component_ids=["C9"],
        implementation_artifacts=[
            "ironframe/context/manager_v1_0.py", "ironframe/context/compression_v1_0.py",
            "ironframe/context/budget_v1_0.py", "ironframe/context/rot_detector_v1_0.py",
            "ironframe/context/skill_tier_v1_0.py", "ironframe/context/telemetry_v1_0.py",
            "ironframe/context/trust_preservation_v1_0.py", "ironframe/context/zones_v1_0.py",
        ],
        verification_artifacts=["c9-context-budget-tests"],
    ))
    rtm.add(RTMEntry(
        requirement_id="IF-REQ-007",
        description="Agents must have explicitly declared roles and autonomy tiers",
        type="safety", source="architecture",
        component_ids=["C17"],
        implementation_artifacts=[
            "ironframe/agent_trust/tiers_v1_0.py", "ironframe/agent_trust/identity_v1_0.py",
            "ironframe/agent_trust/provenance_v1_0.py", "ironframe/agent_trust/anomaly_v1_0.py",
            "ironframe/agent_trust/engine_v1_0.py", "ironframe/agent_trust/kill_switch_v1_0.py",
        ],
        verification_artifacts=["c17-tier-enforcement-tests", "ironframe/tests/test_c17_trust.py"],
    ))
    rtm.add(RTMEntry(
        requirement_id="IF-REQ-008",
        description="All tool calls must go through governed, audited pathways",
        type="safety", source="architecture",
        component_ids=["C12", "C16"],
        implementation_artifacts=[
            "ironframe/tool_governance/governor_v1_0.py", "ironframe/io_schema/validator_v1_0.py",
            "ironframe/io_schema/boundaries_v1_0.py", "ironframe/io_schema/coercion_v1_0.py",
            "ironframe/io_schema/drift_v1_0.py", "ironframe/io_schema/errors_v1_0.py",
            "ironframe/io_schema/registry_v1_0.py",
        ],
        verification_artifacts=["c12-governance-flow-tests", "ironframe/tests/test_c16_schema.py"],
    ))
    rtm.add(RTMEntry(
        requirement_id="IF-REQ-009",
        description="Cost and latency budgets must be actively tracked and enforced per task",
        type="nonfunctional", source="architecture",
        component_ids=["C15"],
        implementation_artifacts=[
            "ironframe/budget/manager_v1_0.py", "ironframe/budget/sla_v1_0.py",
            "ironframe/budget/ledger_v1_0.py", "ironframe/budget/profiles_v1_0.py",
            "ironframe/budget/routing_v1_0.py",
            "ironframe/mal/budget_v1_0.py",  # MAL-layer budget tracker, coexists with C15
        ],
        verification_artifacts=["c15-sla-enforcement-tests", "ironframe/tests/test_c15_budget.py"],
    ))
    rtm.add(RTMEntry(
        requirement_id="IF-REQ-010",
        description="Reliability overhead costs must be visible in the budget ledger, not hidden",
        type="nonfunctional", source="architecture",
        component_ids=["C15"],
        implementation_artifacts=["ironframe/budget/ledger_v1_0.py", "ironframe/budget/telemetry_v1_0.py"],
        verification_artifacts=["c15-overhead-visibility-tests"],
    ))

    # --- IF-REQ-011 through IF-REQ-018: Phase 3 RTM expansion ---

    rtm.add(RTMEntry(
        requirement_id="IF-REQ-011",
        description=(
            "Iron Frame must recover from transient failures via circuit breakers "
            "(circuit_breaker_v1_0.py) and structured retry (retry_v1_0.py)"
        ),
        type="nonfunctional", source="architecture",
        component_ids=["C8"],
        implementation_artifacts=[
            "ironframe/recovery/circuit_breaker_v1_0.py",
            "ironframe/recovery/retry_v1_0.py",
        ],
        verification_artifacts=["ironframe/tests/test_c8_recovery.py"],
    ))
    rtm.add(RTMEntry(
        requirement_id="IF-REQ-012",
        description=(
            "Iron Frame must evaluate component behavior via benchmark scenarios "
            "with pass/fail gates and governance signal checks"
        ),
        type="nonfunctional", source="architecture",
        component_ids=["C13"],
        implementation_artifacts=[
            "ironframe/eval/scenario_v1_0.py", "ironframe/eval/runner_v1_0.py",
            "ironframe/eval/methods_v1_0.py", "ironframe/eval/gates_v1_0.py",
            "ironframe/eval/isolation_v1_0.py", "ironframe/eval/feedback_v1_0.py",
        ],
        verification_artifacts=["ironframe/tests/test_c13_eval.py"],
    ))
    rtm.add(RTMEntry(
        requirement_id="IF-REQ-013",
        description=(
            "Iron Frame must retrieve, validate, and ground outputs against a knowledge base "
            "with freshness tracking and conflict arbitration"
        ),
        type="functional", source="architecture",
        component_ids=["C10"],
        implementation_artifacts=[
            "ironframe/kb/storage_v1_0.py", "ironframe/kb/retrieval_v1_0.py",
            "ironframe/kb/freshness_v1_0.py", "ironframe/kb/grounding_v1_0.py",
            "ironframe/kb/write_v1_0.py", "ironframe/kb/arbitration_v1_0.py",
            "ironframe/kb/policy_v1_0.py", "ironframe/kb/manager_v1_0.py",
            "ironframe/kb/migration_v1_0.py",
        ],
        verification_artifacts=["ironframe/tests/test_c10_kb.py"],
    ))
    rtm.add(RTMEntry(
        requirement_id="IF-REQ-014",
        description=(
            "Iron Frame must detect prompt injection attempts, sanitize inputs, "
            "enforce security gates, and log threats"
        ),
        type="safety", source="architecture",
        component_ids=["C11"],
        implementation_artifacts=[
            "ironframe/security/detection_v1_0.py", "ironframe/security/engine_v1_0.py",
            "ironframe/security/gate_v1_0.py", "ironframe/security/sanitize_v1_0.py",
            "ironframe/security/threat_log_v1_0.py", "ironframe/security/trust_v1_0.py",
        ],
        verification_artifacts=["ironframe/tests/test_c11_security.py"],
    ))
    rtm.add(RTMEntry(
        requirement_id="IF-REQ-015",
        description=(
            "Iron Frame must support pluggable lifecycle hooks at defined extension points "
            "without blocking the critical path"
        ),
        type="functional", source="architecture",
        component_ids=["C4"],
        implementation_artifacts=["ironframe/hooks/engine_v1_0.py"],
        verification_artifacts=["ironframe/tests/test_c4_hooks.py"],
    ))
    rtm.add(RTMEntry(
        requirement_id="IF-REQ-016",
        description=(
            "Iron Frame must maintain a registry of agent skills with metadata "
            "for discovery and routing"
        ),
        type="functional", source="architecture",
        component_ids=["C2"],
        implementation_artifacts=["ironframe/skills/registry_v1_0.py"],
        verification_artifacts=["ironframe/tests/test_c2_skills.py"],
    ))
    rtm.add(RTMEntry(
        requirement_id="IF-REQ-017",
        description=(
            "Iron Frame must track session lifecycle and phase transitions "
            "with persistent, recoverable state"
        ),
        type="nonfunctional", source="architecture",
        component_ids=["C3"],
        implementation_artifacts=[
            "ironframe/state/session_v1_0.py", "ironframe/state/phase_v1_0.py",
        ],
        verification_artifacts=["ironframe/tests/test_c3_state.py"],
    ))
    rtm.add(RTMEntry(
        requirement_id="IF-REQ-018",
        description=(
            "Iron Frame must decompose arguments via Toulmin structure, critical questions "
            "of type (CQoT), and fallacy detection to support structured reasoning audits"
        ),
        type="functional", source="architecture",
        component_ids=["C6"],
        implementation_artifacts=[
            "ironframe/logic/toulmin_v1_0.py", "ironframe/logic/cqot_v1_0.py",
            "ironframe/logic/fallacy_v1_0.py",
        ],
        verification_artifacts=["ironframe/tests/test_c6_logic.py"],
    ))

    return rtm
