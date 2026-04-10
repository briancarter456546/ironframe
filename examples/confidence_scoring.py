"""
Confidence scoring -- the Self-Audit Engine (SAE) in action.

The ConfidenceScorer is a weighted signal aggregator. You pass it a dict of
evaluation signals (each signal being the result of a verification check),
and it returns a score in [0, 1] plus a confidence band.

Signals are pluggable: the scorer comes with base signals, and you can add
domain-specific signals via `add_signal(name, weight)`.

SAE tiers (from SPEC.md):
    Tier 0: Prompt-embedded logic (free)
    Tier 1: Same-model judge call (~$0.001)
    Tier 2: Self-consistency with 3 samples (~$0.01)
    Tier 3: Cross-model verification (Perplexity verifies Claude, ~$0.02)
    Tier 4: Symbolic solver (Z3, ~$0.001)

This example shows the scoring API directly -- no API key required.

Run:
    python examples/confidence_scoring.py
"""

from ironframe.sae.confidence_v1_0 import ConfidenceScorer


def main() -> None:
    scorer = ConfidenceScorer()
    print("=== Iron Frame Confidence Scoring ===\n")
    print(f"Default signals: {scorer.signal_names}\n")

    # Case 1: all verification layers passed
    strong = scorer.score({
        "self_consistency": True,
        "judge_approved": True,
        "cross_model_confirmed": True,
    })
    print("[Case 1] All verification signals passed:")
    print(f"  Score: {strong.score:.3f}")
    print(f"  Band:  {strong.band}")
    print(f"  Layers passed: {strong.layers_passed}/{strong.layers_attempted}")
    print()

    # Case 2: judge passed but cross-model disagreed
    mixed = scorer.score({
        "self_consistency": True,
        "judge_approved": True,
        "cross_model_confirmed": False,
    })
    print("[Case 2] Cross-model verification failed:")
    print(f"  Score: {mixed.score:.3f}")
    print(f"  Band:  {mixed.band}")
    print()

    # Case 3: add a domain signal (e.g. KB corroboration for factual claims)
    scorer.add_signal("kb_corroborated", weight=0.20)
    with_kb = scorer.score({
        "self_consistency": True,
        "judge_approved": True,
        "cross_model_confirmed": True,
        "kb_corroborated": True,
    })
    print("[Case 3] With domain signal 'kb_corroborated' added:")
    print(f"  Score: {with_kb.score:.3f}")
    print(f"  Band:  {with_kb.band}")
    print(f"  Signals: {[s.name for s in with_kb.signals]}")
    print()
    print("In production: route outputs below band=MEDIUM to Tier 3+ or human review.")


if __name__ == "__main__":
    main()
