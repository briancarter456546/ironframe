# ============================================================================
# ironframe/recovery/circuit_breaker_v1_0.py - v1.0
# Last updated: 2026-04-04
# ============================================================================
# Circuit breaker pattern for Iron Frame components.
#
# Tracks error rates per component. When errors exceed threshold, the circuit
# opens (blocks calls) to prevent cascading failures. After a cool-down
# period, allows a single test call (half-open). If it succeeds, closes
# the circuit. If it fails, re-opens.
#
# States: CLOSED (normal) -> OPEN (blocking) -> HALF_OPEN (testing) -> CLOSED
#
# Usage:
#   from ironframe.recovery.circuit_breaker_v1_0 import CircuitBreaker
#   cb = CircuitBreaker('mal.anthropic', failure_threshold=5, cooldown_seconds=60)
#
#   if cb.allow_request():
#       try:
#           result = make_api_call()
#           cb.record_success()
#       except Exception as e:
#           cb.record_failure(str(e))
#   else:
#       # Circuit is open -- use fallback
#       ...
# ============================================================================

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class CircuitState(str, Enum):
    CLOSED = "CLOSED"         # Normal operation
    OPEN = "OPEN"             # Blocking calls
    HALF_OPEN = "HALF_OPEN"   # Testing with single call


@dataclass
class CircuitEvent:
    """Record of a circuit breaker event."""
    timestamp: float
    event_type: str     # 'failure', 'success', 'open', 'close', 'half_open'
    detail: str = ""


class CircuitBreaker:
    """Per-component circuit breaker.

    Thread-safe. Tracks recent failures within a rolling window.
    Opens when failure count exceeds threshold. Re-tests after cooldown.
    """

    def __init__(
        self,
        component: str,
        failure_threshold: int = 5,
        cooldown_seconds: float = 60.0,
        window_seconds: float = 300.0,
    ):
        self.component = component
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.window_seconds = window_seconds

        self._state = CircuitState.CLOSED
        self._failures: List[float] = []  # timestamps of recent failures
        self._last_failure_time = 0.0
        self._opened_at = 0.0
        self._total_failures = 0
        self._total_successes = 0
        self._events: List[CircuitEvent] = []
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_transition()
            return self._state

    def allow_request(self) -> bool:
        """Check if a request is allowed through the circuit.

        CLOSED: always allowed
        OPEN: blocked (check if cooldown elapsed -> HALF_OPEN)
        HALF_OPEN: allow one test request
        """
        with self._lock:
            self._maybe_transition()

            if self._state == CircuitState.CLOSED:
                return True
            elif self._state == CircuitState.HALF_OPEN:
                return True  # allow the test request
            else:
                return False  # OPEN -- blocked

    def record_success(self) -> None:
        """Record a successful call. If half-open, closes the circuit."""
        with self._lock:
            self._total_successes += 1
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._failures.clear()
                self._log_event("close", "Half-open test succeeded, closing circuit")

    def record_failure(self, detail: str = "") -> None:
        """Record a failed call. May open the circuit."""
        now = time.time()
        with self._lock:
            self._total_failures += 1
            self._failures.append(now)
            self._last_failure_time = now
            self._log_event("failure", detail)

            # If half-open, re-open immediately
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = now
                self._log_event("open", "Half-open test failed, re-opening")
                return

            # Prune old failures outside window
            cutoff = now - self.window_seconds
            self._failures = [t for t in self._failures if t > cutoff]

            # Check threshold
            if len(self._failures) >= self.failure_threshold:
                if self._state == CircuitState.CLOSED:
                    self._state = CircuitState.OPEN
                    self._opened_at = now
                    self._log_event("open",
                                    f"{len(self._failures)} failures in {self.window_seconds}s window")

    def _maybe_transition(self) -> None:
        """Check if OPEN circuit should transition to HALF_OPEN."""
        if self._state == CircuitState.OPEN:
            elapsed = time.time() - self._opened_at
            if elapsed >= self.cooldown_seconds:
                self._state = CircuitState.HALF_OPEN
                self._log_event("half_open", f"Cooldown elapsed ({elapsed:.1f}s)")

    def _log_event(self, event_type: str, detail: str) -> None:
        """Record an internal event (for diagnostics)."""
        self._events.append(CircuitEvent(
            timestamp=time.time(),
            event_type=event_type,
            detail=detail,
        ))
        # Keep last 100 events
        if len(self._events) > 100:
            self._events = self._events[-100:]

    def summary(self) -> Dict[str, Any]:
        """Return current circuit breaker state summary."""
        with self._lock:
            self._maybe_transition()
            cutoff = time.time() - self.window_seconds
            recent_failures = len([t for t in self._failures if t > cutoff])
            return {
                "component": self.component,
                "state": self._state.value,
                "recent_failures": recent_failures,
                "failure_threshold": self.failure_threshold,
                "total_failures": self._total_failures,
                "total_successes": self._total_successes,
                "cooldown_seconds": self.cooldown_seconds,
            }


class CircuitBreakerRegistry:
    """Registry of circuit breakers across all components."""

    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get(
        self,
        component: str,
        failure_threshold: int = 5,
        cooldown_seconds: float = 60.0,
    ) -> CircuitBreaker:
        """Get or create a circuit breaker for a component."""
        with self._lock:
            if component not in self._breakers:
                self._breakers[component] = CircuitBreaker(
                    component=component,
                    failure_threshold=failure_threshold,
                    cooldown_seconds=cooldown_seconds,
                )
            return self._breakers[component]

    def summary_all(self) -> List[Dict[str, Any]]:
        """Return summary of all circuit breakers."""
        with self._lock:
            return [cb.summary() for cb in self._breakers.values()]
