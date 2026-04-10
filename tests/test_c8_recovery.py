"""Tests for Component 8: Error Recovery & Resilience (IF-REQ-011)."""
import time

from ironframe.recovery.circuit_breaker_v1_0 import CircuitBreaker, CircuitState
from ironframe.recovery.retry_v1_0 import RetryExecutor, RetryResult


def test_circuit_breaker_instantiates():
    cb = CircuitBreaker("test-component", failure_threshold=3, cooldown_seconds=0.1)
    assert cb.state == CircuitState.CLOSED


def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker("test", failure_threshold=3, cooldown_seconds=60)
    cb.record_failure("err1")
    cb.record_failure("err2")
    cb.record_failure("err3")
    assert cb.state == CircuitState.OPEN


def test_circuit_breaker_rejects_while_open():
    cb = CircuitBreaker("test", failure_threshold=2, cooldown_seconds=60)
    cb.record_failure("err1")
    cb.record_failure("err2")
    assert cb.allow_request() is False


def test_circuit_breaker_resets_after_cooldown():
    cb = CircuitBreaker("test", failure_threshold=2, cooldown_seconds=0.01)
    cb.record_failure("err1")
    cb.record_failure("err2")
    assert cb.state == CircuitState.OPEN
    time.sleep(0.02)
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_retry_executor_instantiates():
    class FakeClient:
        def complete(self, **kwargs):
            return {"text": "ok", "cost_usd": 0.001}
    executor = RetryExecutor(FakeClient(), max_retries=2)
    assert executor.max_retries == 2


def test_retry_succeeds_after_transient_failure():
    call_count = 0

    class FlakeyClient:
        def complete(self, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient error")
            return {"text": "ok", "cost_usd": 0.001}

    executor = RetryExecutor(FlakeyClient(), max_retries=2, backoff_base=0.01)
    result = executor.complete_with_retry(prompt="test")
    assert result.success is True
    assert len(result.attempts) >= 2


def test_retry_gives_up_after_max_attempts():
    class AlwaysFails:
        def complete(self, **kwargs):
            raise RuntimeError("permanent error")

    executor = RetryExecutor(AlwaysFails(), max_retries=2, backoff_base=0.01)
    result = executor.complete_with_retry(prompt="test")
    assert result.success is False
    assert len(result.attempts) >= 2
    assert result.final_error
