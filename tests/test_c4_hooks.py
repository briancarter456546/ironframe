"""Tests for Component 4: Hook Engine (IF-REQ-015)."""
from ironframe.hooks.engine_v1_0 import HookEngine, HookResult


def test_hook_engine_instantiates():
    engine = HookEngine()
    assert engine.events == []


def test_hook_registers_at_extension_point():
    engine = HookEngine()
    engine.register("pre_execution", lambda e: HookResult(allow=True), name="test_hook")
    assert "pre_execution" in engine.events
    hooks = engine.list_hooks("pre_execution")
    assert len(hooks) == 1
    assert hooks[0]["name"] == "test_hook"


def test_hook_fires_when_triggered():
    fired = []
    engine = HookEngine()
    engine.register("pre_execution", lambda e: (fired.append(True), HookResult(allow=True))[1], name="tracker")
    result = engine.fire("pre_execution", {"input": "test"})
    assert result.allow is True
    assert len(fired) == 1


def test_two_hooks_fire_in_order():
    order = []
    engine = HookEngine()
    engine.register("pre_execution",
                     lambda e: (order.append("first"), HookResult(allow=True))[1],
                     name="first", priority=10)
    engine.register("pre_execution",
                     lambda e: (order.append("second"), HookResult(allow=True))[1],
                     name="second", priority=20)
    engine.fire("pre_execution", {})
    assert order == ["first", "second"]


def test_non_blocking_hook_failure_does_not_halt():
    engine = HookEngine()
    engine.register("pre_execution",
                     lambda e: HookResult(allow=False, message="non-blocking fail"),
                     name="soft_hook", blocking=False)
    engine.register("pre_execution",
                     lambda e: HookResult(allow=True),
                     name="next_hook", blocking=True)
    result = engine.fire("pre_execution", {})
    assert result.allow is True
    assert len(result.results) == 2
