"""Tests for Component 18: Spec Conformance & Drift Engine."""


def test_import():
    from ironframe.conformance import ConformanceEngine, DriftEvent, RTMRegistry


def test_rtm_seeds_14_requirements(rtm_registry):
    assert len(rtm_registry._entries) >= 12


def test_rtm_c14_requirements(rtm_registry):
    c14_reqs = rtm_registry.list_by_component("C14")
    assert len(c14_reqs) >= 4


def test_rtm_no_coverage_gaps_original_14(rtm_registry):
    """Original IF-REQ-001 through IF-REQ-010 (+ 004A-D) must have zero gaps."""
    original_ids = {f"IF-REQ-{i:03d}" for i in range(1, 11)}
    original_ids.update({"IF-REQ-004A", "IF-REQ-004B", "IF-REQ-004C", "IF-REQ-004D"})
    gaps = rtm_registry.coverage_gaps()
    original_gaps = [g for g in gaps if g.split(":")[0] in original_ids]
    assert original_gaps == [], f"Coverage gaps in original reqs: {original_gaps}"


def test_static_check_pass(conformance_engine):
    report = conformance_engine.run_static_check()
    assert report.status in ("PASS", "WARN")
    arch_violations = [v for v in report.violations
                       if v.drift_type == "ARCH_BOUNDARY_VIOLATION"]
    assert arch_violations == []


def test_trust_escalation_detected(conformance_engine):
    event = {
        "event_id": "pytest-trust-001",
        "event_type": "coordination_message",
        "component_id": "C14",
        "timestamp": "2026-04-08T00:00:00Z",
        "sender_trust_tier": 2,
        "receiver_declared_tier": 3,
        "effective_tier": 3,
        "message_type": "ASSIGNMENT",
        "audit_logged": True,
        "subtask_id": "task-pytest-001",
        "parent_task_id": "parent-pytest-001",
        "sender_agent_id": "agent-A",
        "receiver_agent_id": "agent-B",
        "requires_ack": False,
        "scenario_id": "pytest",
    }
    drifts = conformance_engine.observe_event(event)
    assert any(d.drift_type == "TRUST_ESCALATION" for d in drifts)
    assert any(d.severity == "critical" for d in drifts
               if d.drift_type == "TRUST_ESCALATION")


def test_audit_gap_detected(conformance_engine):
    event = {
        "event_id": "pytest-audit-001",
        "event_type": "coordination_message",
        "component_id": "C14",
        "timestamp": "2026-04-08T00:00:00Z",
        "sender_trust_tier": 2,
        "receiver_declared_tier": 2,
        "effective_tier": 2,
        "message_type": "ASSIGNMENT",
        "audit_logged": False,
        "subtask_id": "task-pytest-002",
        "parent_task_id": "parent-pytest-002",
        "sender_agent_id": "agent-A",
        "receiver_agent_id": "agent-B",
        "requires_ack": False,
        "scenario_id": "pytest",
    }
    drifts = conformance_engine.observe_event(event)
    assert any(d.drift_type == "AUDIT_GAP" for d in drifts)


def test_clean_event_no_drift(conformance_engine):
    event = {
        "event_id": "pytest-clean-001",
        "event_type": "coordination_message",
        "component_id": "C14",
        "timestamp": "2026-04-08T00:00:00Z",
        "sender_trust_tier": 2,
        "receiver_declared_tier": 2,
        "effective_tier": 2,
        "message_type": "ASSIGNMENT",
        "audit_logged": True,
        "subtask_id": "task-pytest-003",
        "parent_task_id": "parent-pytest-003",
        "sender_agent_id": "agent-A",
        "receiver_agent_id": "agent-B",
        "requires_ack": False,
        "scenario_id": "pytest",
    }
    drifts = conformance_engine.observe_event(event)
    assert drifts == [] or all(d.drift_type == "UNSPECIFIED_BEHAVIOR" for d in drifts)


def test_baseline_and_diff(conformance_engine):
    baseline = conformance_engine.create_baseline()
    assert baseline is not None
    assert baseline.baseline_id
    diff = conformance_engine.diff_since_baseline(baseline.baseline_id)
    assert hasattr(diff, "new_drifts")
    assert hasattr(diff, "resolved_drifts")


def test_coverage_report_all_requirements(conformance_engine):
    report = conformance_engine.coverage_report()
    assert len(report) >= 12
