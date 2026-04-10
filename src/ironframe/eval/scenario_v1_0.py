# ============================================================================
# ironframe/eval/scenario_v1_0.py - v1.0
# Last updated: 2026-04-07
# ============================================================================
# Component 13a: Benchmark Scenario Library
#
# Each scenario declares: input, expected behavior, eval method, RTM linkage,
# and governance signal checks (Brian's additions #1 and #2).
#
# Scenarios without RTM linkage are flagged as untraced.
# ============================================================================

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Risk classes
HAPPY_PATH = "HAPPY_PATH"
EDGE_CASE = "EDGE_CASE"
ADVERSARIAL = "ADVERSARIAL"
REGRESSION = "REGRESSION"

# Eval methods
EXACT_MATCH = "exact_match"
SEMANTIC_SIMILARITY = "semantic_similarity"
BEHAVIORAL_TRACE = "behavioral_trace"
ADVERSARIAL_PROBE = "adversarial_probe"
LLM_JUDGE = "llm_judge"


@dataclass
class EvalScenario:
    """A single evaluation scenario with RTM coverage and governance checks."""

    scenario_id: str
    name: str
    description: str = ""

    # What's being tested
    component: str = ""             # primary: "C10", "C17", etc.
    contract_clause: str = ""       # specific contract requirement
    risk_class: str = HAPPY_PATH
    compliance_domain: str = ""     # "hipaa", "finra", "" = not compliance

    # RTM coverage (Brian's addition #2)
    components: List[str] = field(default_factory=list)     # ["C10", "C17"]
    requirements: List[str] = field(default_factory=list)   # ["IF-REQ-002"]
    metrics: List[str] = field(default_factory=list)        # ["kb_grounding_accuracy"]

    # Test definition
    input_data: Dict[str, Any] = field(default_factory=dict)
    expected_behavior: str = ""     # behavior class, not exact output
    eval_method: str = EXACT_MATCH
    pass_criteria: str = ""         # human-readable

    # Governance signal checks (Brian's addition #1)
    check_arbitration: bool = False   # fail if truth arbitration event fires
    check_freshness: bool = False     # fail if only stale KB used
    check_anomaly: bool = False       # fail if tier downgrade or kill

    version: str = "1.0"

    @property
    def is_traced(self) -> bool:
        """True if scenario has RTM linkage. Untraced = flagged."""
        return len(self.requirements) > 0

    @property
    def is_compliance(self) -> bool:
        return bool(self.compliance_domain)

    @property
    def has_governance_checks(self) -> bool:
        return self.check_arbitration or self.check_freshness or self.check_anomaly

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "component": self.component,
            "risk_class": self.risk_class,
            "compliance_domain": self.compliance_domain,
            "components": self.components,
            "requirements": self.requirements,
            "metrics": self.metrics,
            "eval_method": self.eval_method,
            "is_traced": self.is_traced,
            "is_compliance": self.is_compliance,
            "has_governance_checks": self.has_governance_checks,
            "version": self.version,
        }


@dataclass
class EvalResult:
    """Result of evaluating a single scenario, including governance signals."""

    scenario_id: str
    passed: bool
    eval_method: str
    output: Any = None
    score: float = 0.0             # 0.0-1.0
    detail: str = ""

    # Governance signal checks (Brian's addition #1)
    arbitration_events: int = 0     # from C10
    stale_kb_used: bool = False     # from C10 freshness
    anomaly_score: float = 0.0      # from C17
    tier_downgrades: int = 0        # from C17
    kill_events: int = 0            # from C17

    @property
    def governance_clean(self) -> bool:
        """True if no governance violations during eval."""
        return (self.arbitration_events == 0
                and not self.stale_kb_used
                and self.tier_downgrades == 0
                and self.kill_events == 0)

    @property
    def effective_passed(self) -> bool:
        """A pass is only clean if governance signals are also clean."""
        return self.passed and self.governance_clean

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "passed": self.passed,
            "effective_passed": self.effective_passed,
            "governance_clean": self.governance_clean,
            "eval_method": self.eval_method,
            "score": round(self.score, 4),
            "detail": self.detail,
            "arbitration_events": self.arbitration_events,
            "stale_kb_used": self.stale_kb_used,
            "anomaly_score": round(self.anomaly_score, 4),
            "tier_downgrades": self.tier_downgrades,
            "kill_events": self.kill_events,
        }


class ScenarioLibrary:
    """Managed collection of eval scenarios."""

    def __init__(self):
        self._scenarios: Dict[str, EvalScenario] = {}

    def add(self, scenario: EvalScenario) -> None:
        self._scenarios[scenario.scenario_id] = scenario

    def get(self, scenario_id: str) -> Optional[EvalScenario]:
        return self._scenarios.get(scenario_id)

    def list_all(self) -> List[EvalScenario]:
        return list(self._scenarios.values())

    def list_by_component(self, component: str) -> List[EvalScenario]:
        return [s for s in self._scenarios.values()
                if s.component == component or component in s.components]

    def list_by_risk(self, risk_class: str) -> List[EvalScenario]:
        return [s for s in self._scenarios.values() if s.risk_class == risk_class]

    def list_compliance(self) -> List[EvalScenario]:
        return [s for s in self._scenarios.values() if s.is_compliance]

    def list_untraced(self) -> List[EvalScenario]:
        """Scenarios without RTM linkage — flagged for review."""
        return [s for s in self._scenarios.values() if not s.is_traced]

    def rtm_coverage(self) -> Dict[str, List[str]]:
        """Map of requirement ID -> scenario IDs that cover it."""
        coverage: Dict[str, List[str]] = {}
        for s in self._scenarios.values():
            for req_id in s.requirements:
                coverage.setdefault(req_id, []).append(s.scenario_id)
        return coverage

    def summary(self) -> Dict[str, Any]:
        total = len(self._scenarios)
        return {
            "total": total,
            "by_risk": {rc: len(self.list_by_risk(rc))
                        for rc in [HAPPY_PATH, EDGE_CASE, ADVERSARIAL, REGRESSION]},
            "compliance": len(self.list_compliance()),
            "untraced": len(self.list_untraced()),
            "requirements_covered": len(self.rtm_coverage()),
        }
