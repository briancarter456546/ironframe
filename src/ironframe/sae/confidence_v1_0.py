# ============================================================================
# ironframe/sae/confidence_v1_0.py - v1.0
# Last updated: 2026-04-04
# ============================================================================
# Generalized confidence scoring. Domain-pluggable.
#
# Generalized from scientist_mode_v1_0.py's additive weighted scorer.
# Base signals (model-level) + optional domain signal plugins.
#
# CriticMode correction: made domain-pluggable so the same scorer works
# for trading, healthcare, research, etc. without changing core code.
#
# Usage:
#   from ironframe.sae.confidence_v1_0 import ConfidenceScorer, ConfidenceResult
#
#   scorer = ConfidenceScorer()
#   result = scorer.score({
#       'self_consistency': True,
#       'judge_approved': True,
#       'cross_model_confirmed': False,
#   })
#   print(result.score, result.band)  # 0.667, MEDIUM
#
#   # With domain plugin:
#   scorer.add_signal('kb_corroborated', weight=0.20)
#   result = scorer.score({..., 'kb_corroborated': True})
# ============================================================================

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ConfidenceBand(str, Enum):
    HIGH = "HIGH"               # >= 0.8
    MEDIUM = "MEDIUM"           # >= 0.5
    LOW = "LOW"                 # >= 0.2
    UNACCEPTABLE = "UNACCEPTABLE"  # < 0.2


# Band thresholds (configurable via ConfidenceScorer constructor)
_DEFAULT_THRESHOLDS = {
    ConfidenceBand.HIGH: 0.8,
    ConfidenceBand.MEDIUM: 0.5,
    ConfidenceBand.LOW: 0.2,
}


@dataclass
class SignalResult:
    """Result of a single confidence signal."""
    name: str
    status: str      # 'passed', 'failed', 'skipped'
    weight: float
    points: float    # weight if passed, 0 if failed, 0 if skipped


@dataclass
class ConfidenceResult:
    """Full confidence scoring result."""
    score: float                          # 0.0 - 1.0
    band: str                             # HIGH, MEDIUM, LOW, UNACCEPTABLE
    signals: List[SignalResult]           # per-signal breakdown
    layers_attempted: int = 0
    layers_passed: int = 0
    domain_signals: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "band": self.band,
            "layers_attempted": self.layers_attempted,
            "layers_passed": self.layers_passed,
            "signals": {s.name: {"status": s.status, "weight": s.weight, "points": s.points}
                        for s in self.signals},
            "domain_signals": self.domain_signals,
        }


class ConfidenceScorer:
    """Additive weighted confidence scorer with domain plugins.

    Base signals cover model-level verification. Domain signals can be
    added for application-specific checks (e.g., KB corroboration for
    trading, PHI detection for healthcare).

    Pattern from scientist_mode_v1_0.py: skip-if-not-attempted,
    normalize by attempted weight only.
    """

    # Default base signals (model-level verification)
    _DEFAULT_SIGNALS = {
        "self_consistency":       0.20,  # same answer across samples
        "judge_approved":         0.20,  # LLM-as-judge passed
        "cross_model_confirmed":  0.25,  # different model family agreed
        "reasoning_chain_valid":  0.15,  # CoT steps individually valid
        "no_hallucination_flags": 0.20,  # no detected fabrication
    }

    def __init__(
        self,
        signals: Optional[Dict[str, float]] = None,
        thresholds: Optional[Dict[ConfidenceBand, float]] = None,
    ):
        self._signals = dict(signals or self._DEFAULT_SIGNALS)
        self._thresholds = thresholds or _DEFAULT_THRESHOLDS.copy()

    def add_signal(self, name: str, weight: float) -> None:
        """Add a domain-specific signal. Weights are relative, not required to sum to 1."""
        self._signals[name] = weight

    def remove_signal(self, name: str) -> None:
        """Remove a signal."""
        self._signals.pop(name, None)

    @property
    def signal_names(self) -> List[str]:
        return list(self._signals.keys())

    def score(
        self,
        results: Dict[str, Any],
        domain_signals: Optional[Dict[str, Any]] = None,
    ) -> ConfidenceResult:
        """Compute confidence score from verification results.

        results: signal_name -> True/False (passed/failed) or None (skipped)
        domain_signals: arbitrary domain metadata to attach to result

        Scoring: additive weighted, normalized by attempted weight only.
        Skipped signals are excluded from the denominator.
        """
        signal_results = []
        attempted_weight = 0.0
        earned_weight = 0.0

        for signal_name, weight in self._signals.items():
            result_val = results.get(signal_name)

            if result_val is None:
                signal_results.append(SignalResult(
                    name=signal_name, status="skipped", weight=weight, points=0.0
                ))
                continue

            attempted_weight += weight
            passed = bool(result_val)
            points = weight if passed else 0.0
            earned_weight += points
            signal_results.append(SignalResult(
                name=signal_name,
                status="passed" if passed else "failed",
                weight=weight,
                points=points,
            ))

        final_score = earned_weight / attempted_weight if attempted_weight > 0 else 0.0
        band = self._classify_band(final_score)

        layers_attempted = sum(1 for s in signal_results if s.status != "skipped")
        layers_passed = sum(1 for s in signal_results if s.status == "passed")

        return ConfidenceResult(
            score=round(final_score, 4),
            band=band,
            signals=signal_results,
            layers_attempted=layers_attempted,
            layers_passed=layers_passed,
            domain_signals=domain_signals or {},
        )

    def _classify_band(self, score: float) -> str:
        """Classify score into confidence band."""
        if score >= self._thresholds[ConfidenceBand.HIGH]:
            return ConfidenceBand.HIGH.value
        elif score >= self._thresholds[ConfidenceBand.MEDIUM]:
            return ConfidenceBand.MEDIUM.value
        elif score >= self._thresholds[ConfidenceBand.LOW]:
            return ConfidenceBand.LOW.value
        else:
            return ConfidenceBand.UNACCEPTABLE.value
