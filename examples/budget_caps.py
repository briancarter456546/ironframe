"""
Budget caps -- spend control at per-request, per-session, and per-day levels.

Tier escalation without budget ceilings is a production risk. Iron Frame's
BudgetTracker enforces three levels of caps. check() raises BudgetExhausted
before the call; record() tracks actual spend afterward.

No API key required -- this demonstrates the tracker directly.

Run:
    python examples/budget_caps.py
"""

from ironframe.mal.budget_v1_0 import BudgetExhausted, BudgetTracker


def main() -> None:
    # Tight budget for demonstration
    tracker = BudgetTracker(
        per_request=0.05,   # 5 cents max per single call
        per_session=0.10,   # 10 cents max for the whole session
        per_day=5.00,       # $5 max per day
    )

    print("=== Iron Frame Budget Caps ===\n")
    print(f"Per-request cap: ${tracker.cap_per_request}")
    print(f"Per-session cap: ${tracker.cap_per_session}")
    print(f"Per-day cap:     ${tracker.cap_per_day}\n")

    # Simulate a sequence of calls
    simulated_costs = [0.02, 0.03, 0.04, 0.08]
    for i, cost in enumerate(simulated_costs, 1):
        try:
            tracker.check(estimated_cost=cost)
            tracker.record(actual_cost=cost)
            summary = tracker.summary()
            print(
                f"[OK]    call {i}: ${cost:.2f} -- "
                f"session spent ${summary['session_spent']:.2f}, "
                f"remaining ${summary['session_remaining']:.2f}"
            )
        except BudgetExhausted as exc:
            print(f"[BLOCK] call {i}: ${cost:.2f} -- {exc}")

    print()
    final = tracker.summary()
    print(f"Final session total: ${final['session_spent']:.2f}")
    print(f"Requests completed:  {final['request_count']}")


if __name__ == "__main__":
    main()
