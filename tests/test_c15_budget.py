"""Tests for Component 15: Cost/Latency Budget Manager."""
import time

from ironframe.budget.profiles_v1_0 import TaskBudgetProfile
from ironframe.budget.ledger_v1_0 import BudgetLedger
from ironframe.budget.sla_v1_0 import SLAEnforcer, SLAStatus
from ironframe.budget.manager_v1_0 import CostLatencyManager


def test_task_budget_profile_creation():
    profile = TaskBudgetProfile(
        profile_id="test",
        task_type="test",
        token_budget=10000,
        latency_sla_ms=5000,
        cost_ceiling_usd=0.50,
        enforcement="HARD",
    )
    assert profile.task_type == "test"
    assert profile.token_budget == 10000
    assert profile.enforcement == "HARD"


def test_ledger_records_cost_entry():
    profile = TaskBudgetProfile(
        profile_id="t", task_type="t",
        token_budget=1000, latency_sla_ms=30000,
        cost_ceiling_usd=1.0,
    )
    ledger = BudgetLedger(profile)
    ledger.record_model_call(100, 50, 0.01, 200.0, "test-model")
    assert ledger.total_tokens == 150
    assert ledger.total_cost_usd == 0.01
    assert ledger.total_latency_ms == 200.0


def test_sla_warning_at_60_pct():
    profile = TaskBudgetProfile(
        profile_id="t", task_type="t",
        token_budget=1000, latency_sla_ms=100,
        cost_ceiling_usd=1.0,
    )
    ledger = BudgetLedger(profile)
    # Force elapsed time past 60% of 100ms SLA
    ledger._start_time = time.time() - 0.070  # 70ms ago
    enforcer = SLAEnforcer()
    check = enforcer.check_sla(ledger)
    assert check.status == SLAStatus.WARNING.value


def test_sla_breach_at_100_pct():
    profile = TaskBudgetProfile(
        profile_id="t", task_type="t",
        token_budget=1000, latency_sla_ms=10,
        cost_ceiling_usd=1.0,
    )
    ledger = BudgetLedger(profile)
    # Force elapsed time past 100% of 10ms SLA
    ledger._start_time = time.time() - 0.020  # 20ms ago
    enforcer = SLAEnforcer()
    check = enforcer.check_sla(ledger)
    assert check.status == SLAStatus.BREACHED.value
    assert check.breach_flag is True


def test_routing_signal_on_high_cost():
    profile = TaskBudgetProfile(
        profile_id="t", task_type="t",
        token_budget=1000, latency_sla_ms=60000,
        cost_ceiling_usd=1.0,
    )
    ledger = BudgetLedger(profile)
    # Record cost at 85% of ceiling
    ledger.record_model_call(100, 50, 0.85, 10.0, "model")
    enforcer = SLAEnforcer()
    check = enforcer.check_budget(ledger)
    assert "prefer_lower_cost_model" in check.signals


def test_overhead_tracked_separately():
    profile = TaskBudgetProfile(
        profile_id="t", task_type="t",
        token_budget=1000, latency_sla_ms=30000,
        cost_ceiling_usd=1.0,
    )
    ledger = BudgetLedger(profile)
    ledger.record_model_call(100, 50, 0.10, 100.0, "model")
    ledger.record_overhead(cost_usd=0.02, latency_ms=20.0, detail="schema_check")
    assert ledger.overhead_cost_usd == 0.02
    assert abs(ledger.total_cost_usd - 0.12) < 1e-9
    assert ledger.overhead_pct > 0


def test_manager_session_lifecycle():
    mgr = CostLatencyManager()
    profile = TaskBudgetProfile(
        profile_id="lifecycle", task_type="lifecycle",
        token_budget=5000, latency_sla_ms=30000,
        cost_ceiling_usd=1.0,
    )
    mgr.profiles.register(profile)
    ledger = mgr.start_session("s1", "lifecycle")
    assert ledger is not None
    assert mgr.get_ledger("s1") is not None
    snap = mgr.end_session("s1")
    assert snap is not None
    assert mgr.get_ledger("s1") is None
