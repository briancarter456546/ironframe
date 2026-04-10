# ============================================================================
# ironframe/sae/tiers_v1_0.py - v1.0
# Last updated: 2026-04-04
# ============================================================================
# Verification tier router with budget-aware escalation.
#
# Tier | What                              | Cost    | Implementation
# -----|-----------------------------------|---------|------------------------------
#  0   | Prompt-embedded logic (Toulmin)    | Free    | Prompt addendum, no API call
#  1   | Same-model judge call              | ~$0.001 | judge_v1_0.py via MAL fast
#  2   | Self-consistency (3 samples)       | ~$0.01  | Same model, varied temp
#  3   | Cross-model verification           | ~$0.02  | cross_model_v1_0.py (Perplexity)
#  4   | Symbolic solver (Z3/Prolog)        | ~$0.001 | Deterministic (not yet impl)
#
# Router checks BudgetTracker before escalating.
# Compliance adapters can set minimum tier floors.
# If budget exhausted: return best completed result + confidence disclosure.
#
# Usage:
#   from ironframe.sae.tiers_v1_0 import TierRouter
#   from ironframe.mal import get_client
#
#   client = get_client()
#   router = TierRouter(client)
#   result = router.verify(
#       prompt='What causes inflation?',
#       output_text='Money supply expansion...',
#       min_tier=0, max_tier=3,
#   )
#   print(result)
# ============================================================================

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ironframe.sae.confidence_v1_0 import ConfidenceScorer, ConfidenceBand
from ironframe.sae.judge_v1_0 import Judge
from ironframe.sae.cross_model_v1_0 import CrossModelVerifier
from ironframe.mal.budget_v1_0 import BudgetExhausted


# Estimated costs per tier (used for budget pre-checks)
_TIER_COST_ESTIMATES = {
    0: 0.0,
    1: 0.001,
    2: 0.01,
    3: 0.02,
    4: 0.001,
}


@dataclass
class TierResult:
    """Result of a tier verification pass."""
    tier: int
    passed: bool
    details: Dict[str, Any] = field(default_factory=dict)
    cost_usd: float = 0.0


@dataclass
class VerificationResult:
    """Full verification result across all attempted tiers."""
    highest_tier_completed: int
    tier_results: List[TierResult]
    confidence_score: float
    confidence_band: str
    budget_exhausted: bool = False
    total_cost_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "highest_tier_completed": self.highest_tier_completed,
            "tiers": [{
                "tier": t.tier,
                "passed": t.passed,
                "cost_usd": t.cost_usd,
                "details": t.details,
            } for t in self.tier_results],
            "confidence_score": round(self.confidence_score, 4),
            "confidence_band": self.confidence_band,
            "budget_exhausted": self.budget_exhausted,
            "total_cost_usd": round(self.total_cost_usd, 6),
        }


class TierRouter:
    """Budget-aware verification tier router.

    Escalates through tiers 0-4, checking budget before each.
    Stops at max_tier or when budget is exhausted.
    Returns best result from highest completed tier.
    """

    def __init__(self, client, scorer: Optional[ConfidenceScorer] = None):
        self._client = client
        self._scorer = scorer or ConfidenceScorer()
        self._judge = Judge(client, preference="fast")
        self._cross_model = CrossModelVerifier(client, preference="verification")

    def verify(
        self,
        prompt: str,
        output_text: str,
        min_tier: int = 0,
        max_tier: int = 3,
        min_tier_floor: Optional[int] = None,
        claims: Optional[List[str]] = None,
    ) -> VerificationResult:
        """Run verification through tiers min_tier to max_tier.

        min_tier_floor: compliance adapter can force a minimum (e.g., HIPAA = Tier 2+)
        claims: pre-extracted claims for Tier 3. If None, extracted automatically.
        """
        if min_tier_floor is not None:
            min_tier = max(min_tier, min_tier_floor)

        tier_results = []
        signal_results = {}
        total_cost = 0.0
        budget_exhausted = False

        for tier in range(min_tier, max_tier + 1):
            # Budget pre-check
            estimated = _TIER_COST_ESTIMATES.get(tier, 0.01)
            try:
                if estimated > 0:
                    self._client.budget.check(estimated)
            except BudgetExhausted:
                budget_exhausted = True
                break

            # Execute tier
            if tier == 0:
                result = self._tier_0(prompt, output_text)
            elif tier == 1:
                result = self._tier_1(prompt, output_text)
            elif tier == 2:
                result = self._tier_2(prompt, output_text)
            elif tier == 3:
                result = self._tier_3(prompt, output_text, claims)
            elif tier == 4:
                result = self._tier_4(prompt, output_text)
            else:
                break

            tier_results.append(result)
            total_cost += result.cost_usd

            # Map tier results to confidence signals
            signal_map = {
                0: "reasoning_chain_valid",
                1: "judge_approved",
                2: "self_consistency",
                3: "cross_model_confirmed",
                4: "reasoning_chain_valid",  # symbolic also validates logic
            }
            signal_name = signal_map.get(tier)
            if signal_name:
                signal_results[signal_name] = result.passed

        # Score confidence from all collected signals
        confidence = self._scorer.score(signal_results)

        highest = tier_results[-1].tier if tier_results else -1

        return VerificationResult(
            highest_tier_completed=highest,
            tier_results=tier_results,
            confidence_score=confidence.score,
            confidence_band=confidence.band,
            budget_exhausted=budget_exhausted,
            total_cost_usd=total_cost,
        )

    def _tier_0(self, prompt: str, output_text: str) -> TierResult:
        """Tier 0: Prompt-embedded logic check. Free, no API call.

        Checks structural indicators in the output text:
        - Contains reasoning markers (because, therefore, however)
        - Has qualifiers (not absolute claims)
        - Addresses the prompt topic
        """
        text_lower = output_text.lower()

        has_reasoning = any(w in text_lower for w in
                           ["because", "therefore", "since", "given that",
                            "this means", "as a result", "consequently"])
        has_qualifiers = any(w in text_lower for w in
                            ["likely", "probably", "approximately", "generally",
                             "in most cases", "tends to", "may", "might"])
        addresses_prompt = any(
            word.lower() in text_lower
            for word in prompt.lower().split()[:5]
            if len(word) > 3
        )

        checks = {"has_reasoning": has_reasoning, "has_qualifiers": has_qualifiers,
                   "addresses_prompt": addresses_prompt}
        passed = sum(checks.values()) >= 2

        return TierResult(tier=0, passed=passed, details=checks, cost_usd=0.0)

    def _tier_1(self, prompt: str, output_text: str) -> TierResult:
        """Tier 1: LLM-as-judge. Single cheap model call."""
        verdict = self._judge.evaluate(
            original_prompt=prompt,
            output_text=output_text,
        )
        return TierResult(
            tier=1,
            passed=verdict.get("approved", False),
            details=verdict,
            cost_usd=verdict.get("cost_usd", 0.0),
        )

    def _tier_2(self, prompt: str, output_text: str) -> TierResult:
        """Tier 2: Self-consistency. 3 samples at varied temperature."""
        samples = []
        total_cost = 0.0

        for temp in [0.3, 0.7, 1.0]:
            result = self._client.complete(
                prompt=prompt,
                preference="fast",
                max_tokens=512,
                temperature=temp,
            )
            samples.append(result.get("text", ""))
            total_cost += result.get("cost_usd", 0.0)

        # Check consistency: do samples agree on key claims?
        # Simple heuristic: check if core content words overlap significantly
        def _key_words(text):
            words = set(text.lower().split())
            return {w for w in words if len(w) > 4}

        original_words = _key_words(output_text)
        overlaps = []
        for sample in samples:
            sample_words = _key_words(sample)
            if original_words:
                overlap = len(original_words & sample_words) / len(original_words)
                overlaps.append(overlap)

        avg_overlap = sum(overlaps) / len(overlaps) if overlaps else 0.0
        passed = avg_overlap >= 0.4  # 40% key word overlap = reasonably consistent

        return TierResult(
            tier=2,
            passed=passed,
            details={
                "sample_count": len(samples),
                "avg_overlap": round(avg_overlap, 3),
                "overlaps": [round(o, 3) for o in overlaps],
            },
            cost_usd=total_cost,
        )

    def _tier_3(self, prompt: str, output_text: str,
                claims: Optional[List[str]] = None) -> TierResult:
        """Tier 3: Cross-model verification. Different model family."""
        if claims:
            verdict = self._cross_model.verify(claims)
        else:
            verdict = self._cross_model.verify_text(output_text, original_context=prompt)

        overall = verdict.get("overall_reliable", False)
        degraded = verdict.get("degraded", False)

        return TierResult(
            tier=3,
            passed=overall and not degraded,
            details=verdict,
            cost_usd=verdict.get("cost_usd", 0.0),
        )

    def _tier_4(self, prompt: str, output_text: str) -> TierResult:
        """Tier 4: Symbolic solver (Z3/Prolog). Not yet implemented."""
        return TierResult(
            tier=4,
            passed=False,
            details={"status": "not_implemented",
                     "message": "Symbolic solver (Z3/Prolog) not yet built"},
            cost_usd=0.0,
        )
