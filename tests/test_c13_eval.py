"""Tests for Component 13: Eval Harness (IF-REQ-012)."""
from ironframe.eval.scenario_v1_0 import EvalScenario, EvalResult, ScenarioLibrary, HAPPY_PATH
from ironframe.eval.gates_v1_0 import RegressionGate, GateRegistry


def test_scenario_instantiates():
    s = EvalScenario(
        scenario_id="test-001",
        name="Test scenario",
        component="C13",
        requirements=["IF-REQ-012"],
        eval_method="exact_match",
    )
    assert s.scenario_id == "test-001"
    assert s.is_traced


def test_runner_runs_scenario_returns_result():
    from ironframe.eval.runner_v1_0 import EvalRunner
    lib = ScenarioLibrary()
    lib.add(EvalScenario(
        scenario_id="run-test",
        name="Runner test",
        eval_method="exact_match",
        input_data={"output": "hello", "expected": "hello"},
    ))
    runner = EvalRunner(lib)
    result = runner.run_suite("test-suite")
    assert result.total == 1
    assert result.passed == 1


def test_gate_passes_when_criteria_met():
    gate = RegressionGate(
        gate_id="g1", name="Test gate", component="C13",
        pass_threshold=0.5,
    )
    results = [
        EvalResult(scenario_id="s1", passed=True, eval_method="exact_match", score=1.0),
        EvalResult(scenario_id="s2", passed=True, eval_method="exact_match", score=1.0),
    ]
    gr = gate.check(results)
    assert gr.passed is True


def test_gate_fails_when_criteria_not_met():
    gate = RegressionGate(
        gate_id="g2", name="Strict gate", component="C13",
        pass_threshold=1.0,
    )
    results = [
        EvalResult(scenario_id="s1", passed=True, eval_method="exact_match", score=1.0),
        EvalResult(scenario_id="s2", passed=False, eval_method="exact_match", score=0.0),
    ]
    gr = gate.check(results)
    assert gr.passed is False


def test_scenario_result_includes_pass_fail():
    r = EvalResult(scenario_id="s1", passed=True, eval_method="exact_match")
    assert r.passed is True
    r2 = EvalResult(scenario_id="s2", passed=False, eval_method="exact_match")
    assert r2.passed is False
