# ============================================================================
# ironframe/eval/gates_v1_0.py - v1.0
# Last updated: 2026-04-07
# ============================================================================
# Component 13c: Regression Gates
#
# Pass/fail thresholds that block deployment or release when crossed.
# C18 reads gate results as conformance evidence.
# Compliance gates require 100% pass — any failure blocks release.
# ============================================================================

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ironframe.eval.scenario_v1_0 import EvalResult


@dataclass
class RegressionGate:
    """A pass/fail threshold for a set of eval scenarios."""
    gate_id: str
    name: str
    component: str
    requirement_ids: List[str] = field(default_factory=list)
    pass_threshold: float = 0.95        # 0.0-1.0
    is_release_blocker: bool = True
    is_compliance_gate: bool = False    # compliance = 100% required

    def check(self, results: List[EvalResult]) -> "GateResult":
        """Evaluate gate against a list of eval results.

        Uses effective_passed (governance-aware) for clean pass rate.
        """
        if not results:
            return GateResult(
                gate_id=self.gate_id, passed=False, pass_rate=0.0,
                total=0, effective_passes=0,
                reason="No eval results to check",
            )

        effective_passes = sum(1 for r in results if r.effective_passed)
        total = len(results)
        pass_rate = effective_passes / total

        threshold = 1.0 if self.is_compliance_gate else self.pass_threshold
        passed = pass_rate >= threshold

        reason = ""
        if not passed:
            failures = [r.scenario_id for r in results if not r.effective_passed]
            gov_failures = [r.scenario_id for r in results
                            if r.passed and not r.governance_clean]
            reason = f"Pass rate {pass_rate:.0%} below threshold {threshold:.0%}. "
            if gov_failures:
                reason += f"Governance-degraded: {gov_failures[:5]}. "
            reason += f"Failed: {failures[:5]}"

        return GateResult(
            gate_id=self.gate_id,
            passed=passed,
            pass_rate=round(pass_rate, 4),
            total=total,
            effective_passes=effective_passes,
            is_release_blocker=self.is_release_blocker,
            is_compliance_gate=self.is_compliance_gate,
            reason=reason,
        )


@dataclass
class GateResult:
    """Result of checking a regression gate."""
    gate_id: str
    passed: bool
    pass_rate: float
    total: int
    effective_passes: int
    is_release_blocker: bool = True
    is_compliance_gate: bool = False
    reason: str = ""

    @property
    def blocks_release(self) -> bool:
        return not self.passed and self.is_release_blocker

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "passed": self.passed,
            "pass_rate": self.pass_rate,
            "total": self.total,
            "effective_passes": self.effective_passes,
            "blocks_release": self.blocks_release,
            "is_compliance_gate": self.is_compliance_gate,
            "reason": self.reason,
        }


class GateRegistry:
    """Collection of regression gates."""

    def __init__(self):
        self._gates: Dict[str, RegressionGate] = {}

    def register(self, gate: RegressionGate) -> None:
        self._gates[gate.gate_id] = gate

    def get(self, gate_id: str) -> RegressionGate:
        return self._gates.get(gate_id)

    def check_all(self, results_by_gate: Dict[str, List[EvalResult]]) -> List[GateResult]:
        """Check all gates. Returns list of GateResults."""
        gate_results = []
        for gate_id, gate in self._gates.items():
            results = results_by_gate.get(gate_id, [])
            gate_results.append(gate.check(results))
        return gate_results

    def any_blocker_failed(self, gate_results: List[GateResult]) -> bool:
        """True if any release-blocking gate failed."""
        return any(gr.blocks_release for gr in gate_results)

    def summary(self) -> Dict[str, Any]:
        return {
            "total_gates": len(self._gates),
            "release_blockers": sum(1 for g in self._gates.values() if g.is_release_blocker),
            "compliance_gates": sum(1 for g in self._gates.values() if g.is_compliance_gate),
        }
