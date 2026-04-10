# ============================================================================
# ironframe/eval/scenarios/c18_scenarios.py - v1.0
# Last updated: 2026-04-08
# ============================================================================
# C18 Conformance eval scenarios for the C13 harness.
#
# Three scenarios:
#   c18-static-clean   - static check passes with C14 artifacts present
#   c18-trust-drift    - detects trust escalation drift
#   c18-rtm-gap        - detects RTM coverage gap
# ============================================================================

from ironframe.eval.scenario_v1_0 import (
    EvalScenario, ScenarioLibrary,
    HAPPY_PATH, EDGE_CASE, BEHAVIORAL_TRACE,
)


SCENARIO_STATIC_CLEAN = EvalScenario(
    scenario_id="c18-static-clean",
    name="C18 static check passes with all C14 artifacts present",
    description=(
        "Run engine.run_static_check(). Verify status is PASS or WARN. "
        "No ARCH_BOUNDARY_VIOLATION or INVARIANT_NOT_VERIFIED in violations."
    ),
    component="C18",
    components=["C14", "C18"],
    requirements=["IF-REQ-005"],
    risk_class=HAPPY_PATH,
    eval_method="static_check",
    pass_criteria=(
        "report.status in (PASS, WARN); "
        "no ARCH_BOUNDARY_VIOLATION in violations; "
        "no INVARIANT_NOT_VERIFIED in violations"
    ),
)

SCENARIO_TRUST_DRIFT = EvalScenario(
    scenario_id="c18-trust-drift",
    name="C18 detects trust escalation drift",
    description=(
        "Inject coordination_message event with effective_tier > min(sender, receiver). "
        "Assert TRUST_ESCALATION drift detected with critical severity."
    ),
    component="C18",
    components=["C14", "C18"],
    requirements=["IF-REQ-004A", "IF-REQ-005"],
    risk_class=EDGE_CASE,
    eval_method=BEHAVIORAL_TRACE,
    pass_criteria=(
        "drift_type == TRUST_ESCALATION in engine drifts; "
        "severity == critical"
    ),
    input_data={
        "expected_events": ["TRUST_ESCALATION"],
    },
)

SCENARIO_RTM_GAP = EvalScenario(
    scenario_id="c18-rtm-gap",
    name="C18 detects RTM coverage gap",
    description=(
        "Register a new accepted requirement with empty verification_artifacts. "
        "Run static check. Assert RTM_COVERAGE_GAP in violations."
    ),
    component="C18",
    components=["C18"],
    requirements=["IF-REQ-005"],
    risk_class=EDGE_CASE,
    eval_method="static_check",
    pass_criteria="RTM_COVERAGE_GAP in report.violations",
)


def register_c18_scenarios(library: ScenarioLibrary) -> None:
    """Register all C18 eval scenarios in the ScenarioLibrary."""
    library.add(SCENARIO_STATIC_CLEAN)
    library.add(SCENARIO_TRUST_DRIFT)
    library.add(SCENARIO_RTM_GAP)
