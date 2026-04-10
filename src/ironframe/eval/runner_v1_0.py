# ============================================================================
# ironframe/eval/runner_v1_0.py - v1.0
# Last updated: 2026-04-07
# ============================================================================
# Component 13 Orchestrator: EvalRunner
#
# Runs eval suites, collects results with governance signals,
# checks regression gates, reports to C18 (drift engine).
# ============================================================================

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ironframe.eval.scenario_v1_0 import EvalScenario, EvalResult, ScenarioLibrary
from ironframe.eval.methods_v1_0 import EVAL_METHODS
from ironframe.eval.gates_v1_0 import GateRegistry, GateResult
from ironframe.eval.isolation_v1_0 import EvalEnvironment
from ironframe.audit.logger_v1_0 import AuditLogger


@dataclass
class SuiteResult:
    """Result of running an eval suite."""
    suite_name: str
    total: int = 0
    passed: int = 0
    effective_passed: int = 0
    failed: int = 0
    governance_degraded: int = 0
    untraced: int = 0
    results: List[EvalResult] = field(default_factory=list)
    gate_results: List[GateResult] = field(default_factory=list)
    release_blocked: bool = False
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "total": self.total,
            "passed": self.passed,
            "effective_passed": self.effective_passed,
            "failed": self.failed,
            "governance_degraded": self.governance_degraded,
            "untraced": self.untraced,
            "release_blocked": self.release_blocked,
            "duration_ms": round(self.duration_ms, 2),
            "pass_rate": round(self.passed / self.total, 4) if self.total else 0,
            "effective_pass_rate": round(self.effective_passed / self.total, 4) if self.total else 0,
        }


class EvalRunner:
    """Runs eval scenarios, collects results, checks gates.

    Executor functions are registered per eval method. Each executor
    receives the scenario and environment, returns raw output.
    """

    def __init__(
        self,
        library: ScenarioLibrary,
        gates: Optional[GateRegistry] = None,
        audit_logger: Optional[AuditLogger] = None,
    ):
        self._library = library
        self._gates = gates or GateRegistry()
        self._audit = audit_logger
        self._executors: Dict[str, Callable] = {}

    def register_executor(self, eval_method: str, executor: Callable) -> None:
        """Register a custom executor for an eval method.

        Executor signature: (scenario: EvalScenario, env: EvalEnvironment) -> Any
        """
        self._executors[eval_method] = executor

    def run_suite(
        self,
        suite_name: str,
        scenarios: Optional[List[EvalScenario]] = None,
        env: Optional[EvalEnvironment] = None,
    ) -> SuiteResult:
        """Run a suite of eval scenarios. Returns aggregated results."""
        start = time.time()

        if scenarios is None:
            scenarios = self._library.list_all()

        results = []
        for scenario in scenarios:
            result = self._run_single(scenario, env)
            results.append(result)

        # Aggregate
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        effective = sum(1 for r in results if r.effective_passed)
        gov_degraded = sum(1 for r in results if r.passed and not r.governance_clean)
        untraced = sum(1 for s in scenarios if not s.is_traced)

        # Check gates
        gate_results = []
        if self._gates:
            # Group results by component for gate checking
            by_component: Dict[str, List[EvalResult]] = {}
            for s, r in zip(scenarios, results):
                key = s.component or "default"
                by_component.setdefault(key, []).append(r)
            gate_results = self._gates.check_all(by_component)

        release_blocked = self._gates.any_blocker_failed(gate_results) if gate_results else False
        elapsed = (time.time() - start) * 1000

        suite_result = SuiteResult(
            suite_name=suite_name,
            total=total,
            passed=passed,
            effective_passed=effective,
            failed=total - passed,
            governance_degraded=gov_degraded,
            untraced=untraced,
            results=results,
            gate_results=gate_results,
            release_blocked=release_blocked,
            duration_ms=elapsed,
        )

        self._log_suite(suite_result)
        return suite_result

    def _run_single(self, scenario: EvalScenario,
                     env: Optional[EvalEnvironment]) -> EvalResult:
        """Run a single scenario and produce an EvalResult."""
        method = scenario.eval_method

        # Try custom executor first, then built-in methods
        executor = self._executors.get(method)
        if executor:
            try:
                output = executor(scenario, env)
            except Exception as e:
                return EvalResult(
                    scenario_id=scenario.scenario_id,
                    passed=False,
                    eval_method=method,
                    detail=f"Executor error: {e}",
                )
        else:
            output = scenario.input_data.get("output", "")

        # Evaluate using built-in method
        eval_fn = EVAL_METHODS.get(method)
        if eval_fn and method in ("exact_match", "semantic_similarity"):
            expected = scenario.input_data.get("expected", scenario.expected_behavior)
            eval_result = eval_fn(output, expected)
        elif eval_fn and method == "behavioral_trace":
            expected_events = scenario.input_data.get("expected_events", [])
            audit_events = scenario.input_data.get("audit_events", [])
            eval_result = eval_fn(audit_events, expected_events)
        elif eval_fn and method == "adversarial_probe":
            eval_result = eval_fn(str(output))
        else:
            eval_result = {"passed": False, "score": 0.0,
                           "detail": f"No evaluator for method '{method}'"}

        return EvalResult(
            scenario_id=scenario.scenario_id,
            passed=eval_result.get("passed", False),
            eval_method=method,
            output=output,
            score=eval_result.get("score", 0.0),
            detail=eval_result.get("detail", ""),
            # Governance signals would be populated by the executor
            # when running against real C10/C17 infrastructure
            arbitration_events=eval_result.get("arbitration_events", 0),
            stale_kb_used=eval_result.get("stale_kb_used", False),
            anomaly_score=eval_result.get("anomaly_score", 0.0),
            tier_downgrades=eval_result.get("tier_downgrades", 0),
            kill_events=eval_result.get("kill_events", 0),
        )

    def _log_suite(self, suite: SuiteResult) -> None:
        if not self._audit:
            return
        try:
            self._audit.log_event(
                event_type="eval.suite_completed",
                component="eval.runner",
                details={
                    "suite_name": suite.suite_name,
                    "total": suite.total,
                    "passed": suite.passed,
                    "effective_passed": suite.effective_passed,
                    "governance_degraded": suite.governance_degraded,
                    "release_blocked": suite.release_blocked,
                    "duration_ms": suite.duration_ms,
                },
            )
        except Exception:
            pass
