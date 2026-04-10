# ============================================================================
# ironframe/mal/budget_v1_0.py - v1.0
# Last updated: 2026-04-04
# ============================================================================
# Spend caps for Iron Frame MAL. Per-request, per-session, per-day.
#
# CriticMode correction: tier escalation without budget ceiling is a
# production risk. Router checks budget before each call.
#
# Usage:
#   from ironframe.mal.budget_v1_0 import BudgetTracker
#   budget = BudgetTracker(per_request=0.50, per_session=5.00, per_day=25.00)
#   budget.check(estimated_cost=0.02)       # raises BudgetExhausted if over
#   budget.record(actual_cost=0.015)        # record after call completes
#   budget.summary()                        # {'session_spent': ..., ...}
# ============================================================================

import threading
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Dict


class BudgetExhausted(Exception):
    """Raised when a spend cap would be exceeded."""

    def __init__(self, cap_name: str, cap_value: float, current_spend: float, requested: float):
        self.cap_name = cap_name
        self.cap_value = cap_value
        self.current_spend = current_spend
        self.requested = requested
        super().__init__(
            f"Budget exhausted: {cap_name} cap ${cap_value:.4f}, "
            f"spent ${current_spend:.4f}, requested ${requested:.4f}"
        )


class BudgetTracker:
    """Tracks and enforces spend caps across request, session, and day.

    Thread-safe. All amounts in USD.
    """

    def __init__(
        self,
        per_request: float = 0.50,
        per_session: float = 5.00,
        per_day: float = 25.00,
    ):
        self.cap_per_request = per_request
        self.cap_per_session = per_session
        self.cap_per_day = per_day

        self._session_spent = 0.0
        self._day_spent = 0.0
        self._current_day = date.today()
        self._request_count = 0
        self._lock = threading.Lock()

    def _maybe_reset_day(self) -> None:
        """Reset daily counter if the date has changed."""
        today = date.today()
        if today != self._current_day:
            self._day_spent = 0.0
            self._current_day = today

    def check(self, estimated_cost: float) -> bool:
        """Check if estimated_cost fits within all caps. Raises BudgetExhausted if not.

        Call BEFORE making an API request. Returns True if OK.
        """
        with self._lock:
            self._maybe_reset_day()

            if estimated_cost > self.cap_per_request:
                raise BudgetExhausted(
                    "per_request", self.cap_per_request, 0.0, estimated_cost
                )

            if self._session_spent + estimated_cost > self.cap_per_session:
                raise BudgetExhausted(
                    "per_session", self.cap_per_session, self._session_spent, estimated_cost
                )

            if self._day_spent + estimated_cost > self.cap_per_day:
                raise BudgetExhausted(
                    "per_day", self.cap_per_day, self._day_spent, estimated_cost
                )

        return True

    def record(self, actual_cost: float) -> None:
        """Record actual cost after a completed API call."""
        with self._lock:
            self._maybe_reset_day()
            self._session_spent += actual_cost
            self._day_spent += actual_cost
            self._request_count += 1

    def remaining(self) -> Dict[str, float]:
        """Return remaining budget for each cap level."""
        with self._lock:
            self._maybe_reset_day()
            return {
                "per_request": self.cap_per_request,
                "per_session": max(0.0, self.cap_per_session - self._session_spent),
                "per_day": max(0.0, self.cap_per_day - self._day_spent),
            }

    def summary(self) -> Dict[str, float]:
        """Return current spend summary."""
        with self._lock:
            self._maybe_reset_day()
            return {
                "session_spent": round(self._session_spent, 6),
                "day_spent": round(self._day_spent, 6),
                "request_count": self._request_count,
                "session_remaining": round(max(0.0, self.cap_per_session - self._session_spent), 6),
                "day_remaining": round(max(0.0, self.cap_per_day - self._day_spent), 6),
            }
