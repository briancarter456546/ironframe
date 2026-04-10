"""Tests for cross-component wiring (Phase 3 gaps)."""
import time

import pytest


def test_c14_to_c18_wired():
    from ironframe.coordination import protocol_v1_0
    assert hasattr(protocol_v1_0, "register_conformance_engine")


def test_c15_to_c18_wired():
    from ironframe.budget.manager_v1_0 import CostLatencyManager
    mgr = CostLatencyManager()
    assert hasattr(mgr, "register_conformance_engine")


def test_c18_to_c13_wired(scenario_library):
    assert scenario_library.get("c18-static-clean") is not None
    assert scenario_library.get("c18-trust-drift") is not None
    assert scenario_library.get("c18-rtm-gap") is not None


def test_trust_escalation_reaches_engine_via_wiring(wired_engine):
    engine, _ = wired_engine
    event = {
        "event_id": "wire-trust-001",
        "event_type": "coordination_message",
        "component_id": "C14",
        "timestamp": "2026-04-08T00:00:00Z",
        "sender_trust_tier": 2,
        "receiver_declared_tier": 3,
        "effective_tier": 3,
        "message_type": "ASSIGNMENT",
        "audit_logged": True,
        "subtask_id": "task-wire-001",
        "parent_task_id": "parent-wire-001",
        "sender_agent_id": "agent-A",
        "receiver_agent_id": "agent-B",
        "requires_ack": False,
        "scenario_id": "wire-test",
    }
    drifts = engine.observe_event(event)
    assert any(d.drift_type == "TRUST_ESCALATION" for d in drifts)


def test_sla_breach_reaches_engine_via_wiring(wired_engine):
    engine, mgr = wired_engine
    from ironframe.budget.profiles_v1_0 import TaskBudgetProfile
    profile = TaskBudgetProfile(
        profile_id="wire-sla-test",
        task_type="wire-sla-test",
        token_budget=1000,
        latency_sla_ms=1,
        cost_ceiling_usd=1.0,
        enforcement="SOFT",
    )
    mgr.profiles.register(profile)
    ledger = mgr.start_session("wire-sla-session", "wire-sla-test")
    time.sleep(0.01)
    ledger.record_model_call(10, 10, 0.01, 5.0, "test-model")
    check = mgr.check_budget("wire-sla-session")
    assert check.sla_status != "normal"
    summary = engine.summary()
    assert summary["monitor"]["events_observed"] > 0
