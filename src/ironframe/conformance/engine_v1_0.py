# ============================================================================
# ironframe/conformance/engine_v1_0.py - v1.0
# Last updated: 2026-04-08
# ============================================================================
# Component 18 Orchestrator: ConformanceEngine
#
# Ties together RTM (18a), static checker (18b), runtime monitor (18c),
# and drift reporter (18d). Provides unified interface for conformance
# checking, drift detection, and compliance queries.
# ============================================================================

from typing import Any, Callable, Dict, List, Optional

from ironframe.conformance.rtm_v1_0 import RTMRegistry, RTMEntry, seed_rtm
from ironframe.conformance.static_checker_v1_0 import StaticConformanceChecker, StaticConformanceReport
from ironframe.conformance.runtime_monitor_v1_0 import (
    RuntimeMonitor, DriftEvent, DriftType, Invariant, register_c14_invariants,
)
from ironframe.conformance.drift_reporter_v1_0 import DriftReporter, Baseline, DriftDiff
from ironframe.audit.logger_v1_0 import AuditLogger


class ConformanceEngine:
    """Component 18 orchestrator.

    Unified interface for:
      - RTM management
      - Static conformance checks (CI/CD gate)
      - Runtime invariant monitoring
      - Drift reporting and baseline management
      - Compliance queries
    """

    def __init__(
        self,
        audit_logger: Optional[AuditLogger] = None,
        contracts_dir: str = "ironframe/contracts",
        code_dir: str = "ironframe",
        auto_seed_rtm: bool = True,
        auto_register_c14: bool = True,
    ):
        self._audit = audit_logger

        # 18a: RTM
        self._rtm = seed_rtm() if auto_seed_rtm else RTMRegistry()

        # 18b: Static checker
        self._static = StaticConformanceChecker(self._rtm, contracts_dir, code_dir)

        # 18c: Runtime monitor
        self._monitor = RuntimeMonitor(audit_logger)
        if auto_register_c14:
            register_c14_invariants(self._monitor)

        # 18d: Drift reporter
        self._reporter = DriftReporter(self._rtm, self._monitor)

    # --- Properties ---

    @property
    def rtm(self) -> RTMRegistry:
        return self._rtm

    @property
    def monitor(self) -> RuntimeMonitor:
        return self._monitor

    @property
    def reporter(self) -> DriftReporter:
        return self._reporter

    # --- RTM management ---

    def add_requirement(self, entry: RTMEntry) -> None:
        self._rtm.add(entry)

    def get_requirement(self, req_id: str) -> Optional[RTMEntry]:
        return self._rtm.get(req_id)

    # --- Static checks ---

    def run_static_check(self) -> StaticConformanceReport:
        """Run static conformance checker (CI/CD gate)."""
        report = self._static.run()
        self._log("conformance.static_check", {
            "status": report.status,
            "violations": len(report.violations),
            "coverage_pct": report.coverage_pct,
        })
        return report

    # --- Runtime monitoring ---

    def observe_event(self, event: Dict[str, Any]) -> List[DriftEvent]:
        """Feed a trace event to the runtime monitor."""
        return self._monitor.observe(event)

    def register_invariant(self, invariant: Invariant) -> None:
        self._monitor.register_invariant(invariant)

    def register_callback(self, drift_type: str, callback: Callable) -> None:
        self._monitor.register_callback(drift_type, callback)

    # --- Baselines and drift reporting ---

    def create_baseline(self) -> Baseline:
        """Snapshot current conformance state."""
        baseline = self._reporter.create_baseline()
        self._log("conformance.baseline_created", baseline.to_dict())
        return baseline

    def diff_since_baseline(self, baseline_id: str) -> DriftDiff:
        return self._reporter.diff_since_baseline(baseline_id)

    def open_drifts(self, component_id: str = "") -> List[DriftEvent]:
        if component_id:
            return self._reporter.open_drifts_by_component(component_id)
        return self._monitor.get_drift_events(status="open")

    # --- Queries ---

    def coverage_report(self) -> Dict[str, Dict[str, Any]]:
        return self._reporter.coverage_report()

    def untested_requirements(self) -> List[str]:
        return self._reporter.untested_requirements()

    def compliance_query(self, regulation_id: str = "", requirement_id: str = "") -> List[Dict[str, Any]]:
        return self._reporter.compliance_query(regulation_id, requirement_id)

    # --- Diagnostics ---

    def summary(self) -> Dict[str, Any]:
        return {
            "rtm": self._rtm.summary(),
            "monitor": self._monitor.summary(),
            "reporter": self._reporter.summary(),
        }

    def _log(self, event_type: str, details: Dict[str, Any]) -> None:
        if not self._audit:
            return
        try:
            self._audit.log_event(
                event_type=event_type,
                component="conformance.engine",
                details=details,
            )
        except Exception:
            pass
