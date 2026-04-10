# ============================================================================
# ironframe/agent_trust/anomaly_v1_0.py - v1.0
# Last updated: 2026-04-07
# ============================================================================
# Component 17c: Behavioral Baseline & Anomaly Detection
#
# v1: rule-based. Each agent type has a declared baseline. Observed
# behavior is compared against it. Anomaly scores above threshold
# trigger tier downgrade + audit event.
#
# v2 path: embedding-based or statistical anomaly detection.
# ============================================================================

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class AgentBaseline:
    """Declared behavioral baseline for an agent type."""
    agent_type: str
    expected_tool_patterns: List[str] = field(default_factory=list)
    expected_confidence_range: Tuple[float, float] = (0.3, 1.0)
    max_kb_queries_per_step: int = 20
    max_tool_calls_per_step: int = 10
    max_steps_per_session: int = 100
    allowed_output_schemas: List[str] = field(default_factory=list)


# Default baselines (overridable per agent type registration)
_DEFAULT_BASELINE = AgentBaseline(agent_type="default")


@dataclass
class AnomalySignal:
    """A single anomaly observation."""
    signal_type: str        # tool_outside_baseline, low_confidence, excessive_queries,
                            # excessive_tool_calls, excessive_steps, self_elevation_attempt
    severity: float         # 0.0-1.0
    detail: str
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_type": self.signal_type,
            "severity": self.severity,
            "detail": self.detail,
            "timestamp": self.timestamp,
        }


@dataclass
class AnomalyAssessment:
    """Aggregate anomaly assessment for a session."""
    session_id: str
    agent_type: str
    score: float                    # 0.0-1.0, aggregate
    signals: List[AnomalySignal] = field(default_factory=list)
    tier_downgrade_recommended: bool = False
    recommended_tier: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "agent_type": self.agent_type,
            "score": round(self.score, 4),
            "signal_count": len(self.signals),
            "tier_downgrade_recommended": self.tier_downgrade_recommended,
            "recommended_tier": self.recommended_tier,
            "signals": [s.to_dict() for s in self.signals],
        }


# Anomaly score thresholds
DOWNGRADE_THRESHOLD = 0.5    # score above this = recommend tier downgrade
CRITICAL_THRESHOLD = 0.8     # score above this = recommend kill switch


class AnomalyDetector:
    """Rule-based behavioral anomaly detection.

    Compares observed agent behavior against declared baselines.
    Produces an anomaly score and individual signals.
    """

    def __init__(self):
        self._baselines: Dict[str, AgentBaseline] = {}
        self._session_observations: Dict[str, Dict[str, Any]] = {}

    def register_baseline(self, baseline: AgentBaseline) -> None:
        """Register a behavioral baseline for an agent type."""
        self._baselines[baseline.agent_type] = baseline

    def get_baseline(self, agent_type: str) -> AgentBaseline:
        return self._baselines.get(agent_type, _DEFAULT_BASELINE)

    def observe_tool_call(self, session_id: str, tool_id: str) -> None:
        """Record a tool call observation for a session."""
        obs = self._get_observations(session_id)
        obs.setdefault("tool_calls", []).append(tool_id)

    def observe_kb_query(self, session_id: str) -> None:
        """Record a KB query observation."""
        obs = self._get_observations(session_id)
        obs["kb_queries"] = obs.get("kb_queries", 0) + 1

    def observe_confidence(self, session_id: str, score: float) -> None:
        """Record a confidence score observation."""
        obs = self._get_observations(session_id)
        obs.setdefault("confidence_scores", []).append(score)

    def observe_step(self, session_id: str) -> None:
        """Record a step completion."""
        obs = self._get_observations(session_id)
        obs["steps"] = obs.get("steps", 0) + 1

    def observe_self_elevation_attempt(self, session_id: str, claimed_tier: int,
                                        actual_tier: int) -> None:
        """Record an agent's attempt to self-declare a higher tier.

        Clarification: this is always an anomaly, never honored.
        """
        obs = self._get_observations(session_id)
        obs.setdefault("self_elevation_attempts", []).append({
            "claimed": claimed_tier,
            "actual": actual_tier,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def assess(self, session_id: str, agent_type: str) -> AnomalyAssessment:
        """Compute aggregate anomaly assessment for a session."""
        baseline = self.get_baseline(agent_type)
        obs = self._get_observations(session_id)
        signals = []

        # Check tool calls outside baseline
        tool_calls = obs.get("tool_calls", [])
        if baseline.expected_tool_patterns:
            unexpected = [t for t in tool_calls if t not in baseline.expected_tool_patterns]
            if unexpected:
                signals.append(AnomalySignal(
                    signal_type="tool_outside_baseline",
                    severity=min(1.0, len(unexpected) * 0.2),
                    detail=f"{len(unexpected)} unexpected tool calls: {unexpected[:5]}",
                ))

        # Check excessive tool calls
        if len(tool_calls) > baseline.max_tool_calls_per_step:
            signals.append(AnomalySignal(
                signal_type="excessive_tool_calls",
                severity=0.4,
                detail=f"{len(tool_calls)} calls vs max {baseline.max_tool_calls_per_step}",
            ))

        # Check KB query volume (exfiltration pattern)
        kb_queries = obs.get("kb_queries", 0)
        if kb_queries > baseline.max_kb_queries_per_step:
            signals.append(AnomalySignal(
                signal_type="excessive_queries",
                severity=0.5,
                detail=f"{kb_queries} KB queries vs max {baseline.max_kb_queries_per_step}",
            ))

        # Check confidence scores
        confidence_scores = obs.get("confidence_scores", [])
        if confidence_scores:
            low_scores = [s for s in confidence_scores
                          if s < baseline.expected_confidence_range[0]]
            if len(low_scores) > len(confidence_scores) * 0.5:
                signals.append(AnomalySignal(
                    signal_type="low_confidence",
                    severity=0.3,
                    detail=f"{len(low_scores)}/{len(confidence_scores)} scores below threshold",
                ))

        # Check step count
        steps = obs.get("steps", 0)
        if steps > baseline.max_steps_per_session:
            signals.append(AnomalySignal(
                signal_type="excessive_steps",
                severity=0.4,
                detail=f"{steps} steps vs max {baseline.max_steps_per_session}",
            ))

        # Check self-elevation attempts (always anomalous)
        elevation_attempts = obs.get("self_elevation_attempts", [])
        if elevation_attempts:
            signals.append(AnomalySignal(
                signal_type="self_elevation_attempt",
                severity=0.8,  # high severity — this is always bad
                detail=f"{len(elevation_attempts)} self-elevation attempts",
            ))

        # Aggregate score
        if signals:
            score = min(1.0, sum(s.severity for s in signals) / max(len(signals), 1))
        else:
            score = 0.0

        # Recommendation
        downgrade = score >= DOWNGRADE_THRESHOLD
        recommended_tier = 1 if score >= CRITICAL_THRESHOLD else (2 if downgrade else 0)

        return AnomalyAssessment(
            session_id=session_id,
            agent_type=agent_type,
            score=score,
            signals=signals,
            tier_downgrade_recommended=downgrade,
            recommended_tier=recommended_tier,
        )

    def clear_session(self, session_id: str) -> None:
        """Clear observations for a session."""
        self._session_observations.pop(session_id, None)

    def _get_observations(self, session_id: str) -> Dict[str, Any]:
        if session_id not in self._session_observations:
            self._session_observations[session_id] = {}
        return self._session_observations[session_id]
