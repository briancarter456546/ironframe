# ============================================================================
# ironframe/eval/feedback_v1_0.py - v1.0
# Last updated: 2026-04-07
# ============================================================================
# Component 13d: Production Feedback Loop
#
# v1: manual feedback — production failure patterns are manually added
# as new regression scenarios. v2: auto-sampling of production traces.
#
# Closes the loop: production failures become eval scenarios so they
# cannot recur undetected.
# ============================================================================

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ironframe.eval.scenario_v1_0 import EvalScenario, REGRESSION


@dataclass
class ProductionFailure:
    """A production failure pattern captured for regression testing."""
    failure_id: str
    description: str
    component: str
    input_pattern: Dict[str, Any] = field(default_factory=dict)
    observed_output: str = ""
    expected_behavior: str = ""
    root_cause: str = ""
    discovered_at: str = ""
    scenario_id: str = ""       # linked regression scenario once created

    def __post_init__(self):
        if not self.discovered_at:
            self.discovered_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "failure_id": self.failure_id,
            "description": self.description,
            "component": self.component,
            "root_cause": self.root_cause,
            "discovered_at": self.discovered_at,
            "has_scenario": bool(self.scenario_id),
        }


class FeedbackCollector:
    """Collects production failures and converts them to regression scenarios."""

    def __init__(self):
        self._failures: List[ProductionFailure] = []

    def report_failure(self, failure: ProductionFailure) -> None:
        """Record a production failure for future regression testing."""
        self._failures.append(failure)

    def create_regression_scenario(self, failure: ProductionFailure,
                                    requirements: Optional[List[str]] = None) -> EvalScenario:
        """Convert a production failure into a regression eval scenario.

        This closes the loop: the failure becomes a permanent test.
        """
        scenario = EvalScenario(
            scenario_id=f"regression_{failure.failure_id}",
            name=f"Regression: {failure.description[:60]}",
            description=f"Auto-generated from production failure {failure.failure_id}. "
                        f"Root cause: {failure.root_cause}",
            component=failure.component,
            risk_class=REGRESSION,
            components=[failure.component],
            requirements=requirements or [],
            metrics=["regression_prevention"],
            input_data=failure.input_pattern,
            expected_behavior=failure.expected_behavior,
            eval_method="exact_match",
            pass_criteria=f"Must not reproduce failure: {failure.description[:80]}",
        )
        failure.scenario_id = scenario.scenario_id
        return scenario

    def unlinked_failures(self) -> List[ProductionFailure]:
        """Failures without a linked regression scenario."""
        return [f for f in self._failures if not f.scenario_id]

    def summary(self) -> Dict[str, Any]:
        return {
            "total_failures": len(self._failures),
            "with_scenarios": sum(1 for f in self._failures if f.scenario_id),
            "unlinked": len(self.unlinked_failures()),
        }
