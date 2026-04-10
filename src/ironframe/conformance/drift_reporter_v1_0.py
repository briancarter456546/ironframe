# ============================================================================
# ironframe/conformance/drift_reporter_v1_0.py - v1.0
# Last updated: 2026-04-08
# ============================================================================
# Component 18d: Drift Differential Reporter
#
# Maintains baselines. Computes deltas between current state and last
# accepted baseline. Provides structured queries for compliance and audit.
# ============================================================================

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ironframe.conformance.rtm_v1_0 import RTMRegistry
from ironframe.conformance.runtime_monitor_v1_0 import RuntimeMonitor, DriftEvent


@dataclass
class Baseline:
    """A snapshot of conformance state at a point in time."""
    baseline_id: str
    timestamp: str
    requirements_total: int
    requirements_complete: int
    coverage_pct: float
    open_drift_count: int
    drift_by_type: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "baseline_id": self.baseline_id,
            "timestamp": self.timestamp,
            "requirements_total": self.requirements_total,
            "requirements_complete": self.requirements_complete,
            "coverage_pct": round(self.coverage_pct, 2),
            "open_drift_count": self.open_drift_count,
            "drift_by_type": self.drift_by_type,
        }


@dataclass
class DriftDiff:
    """Difference between current state and a baseline."""
    baseline_id: str
    new_drifts: List[DriftEvent] = field(default_factory=list)
    resolved_drifts: List[str] = field(default_factory=list)  # drift_event_ids
    coverage_delta: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "baseline_id": self.baseline_id,
            "new_drift_count": len(self.new_drifts),
            "resolved_count": len(self.resolved_drifts),
            "coverage_delta": round(self.coverage_delta, 2),
            "new_drifts": [d.to_dict() for d in self.new_drifts],
        }


class DriftReporter:
    """Manages baselines and provides conformance queries."""

    def __init__(self, rtm: RTMRegistry, monitor: RuntimeMonitor):
        self._rtm = rtm
        self._monitor = monitor
        self._baselines: Dict[str, Baseline] = {}
        self._latest_baseline_id: str = ""

    def create_baseline(self) -> Baseline:
        """Snapshot current conformance state as a new baseline."""
        rtm_summary = self._rtm.summary()
        monitor_summary = self._monitor.summary()

        total = rtm_summary.get("accepted", 0)
        complete = total - rtm_summary.get("coverage_gaps", 0)
        coverage = (complete / total * 100) if total > 0 else 0.0

        baseline = Baseline(
            baseline_id=str(uuid.uuid4())[:12],
            timestamp=datetime.now(timezone.utc).isoformat(),
            requirements_total=total,
            requirements_complete=complete,
            coverage_pct=coverage,
            open_drift_count=monitor_summary.get("open_drifts", 0),
            drift_by_type=monitor_summary.get("by_type", {}),
        )

        self._baselines[baseline.baseline_id] = baseline
        self._latest_baseline_id = baseline.baseline_id
        return baseline

    def diff_since_baseline(self, baseline_id: str) -> DriftDiff:
        """Compute drift delta since a baseline."""
        baseline = self._baselines.get(baseline_id)
        if not baseline:
            return DriftDiff(baseline_id=baseline_id)

        # Get all drift events after baseline timestamp
        all_drifts = self._monitor.get_drift_events()
        new_drifts = [d for d in all_drifts if d.timestamp > baseline.timestamp and d.status == "open"]
        resolved = [d.drift_event_id for d in all_drifts
                     if d.timestamp > baseline.timestamp and d.status == "mitigated"]

        # Coverage delta
        current_summary = self._rtm.summary()
        current_total = current_summary.get("accepted", 0)
        current_complete = current_total - current_summary.get("coverage_gaps", 0)
        current_pct = (current_complete / current_total * 100) if current_total > 0 else 0.0
        delta = current_pct - baseline.coverage_pct

        return DriftDiff(
            baseline_id=baseline_id,
            new_drifts=new_drifts,
            resolved_drifts=resolved,
            coverage_delta=delta,
        )

    def open_drifts_by_component(self, component_id: str) -> List[DriftEvent]:
        """All open drift events for a component."""
        return self._monitor.get_drift_events(component_id=component_id, status="open")

    def coverage_report(self) -> Dict[str, Dict[str, Any]]:
        """Per-requirement coverage status."""
        return self._rtm.coverage_report()

    def untested_requirements(self) -> List[str]:
        """Requirements never exercised in runtime."""
        return self._rtm.untested_requirements()

    def compliance_query(self, regulation_id: str = "", requirement_id: str = "") -> List[Dict[str, Any]]:
        """Query requirements + implementation + tests + evidence for a regulation or requirement."""
        return self._rtm.compliance_query(regulation_id=regulation_id, requirement_id=requirement_id)

    def get_baseline(self, baseline_id: str) -> Optional[Baseline]:
        return self._baselines.get(baseline_id)

    @property
    def latest_baseline(self) -> Optional[Baseline]:
        return self._baselines.get(self._latest_baseline_id)

    def summary(self) -> Dict[str, Any]:
        return {
            "baselines": len(self._baselines),
            "latest_baseline_id": self._latest_baseline_id,
            "rtm": self._rtm.summary(),
            "monitor": self._monitor.summary(),
        }
