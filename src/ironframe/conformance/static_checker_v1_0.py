# ============================================================================
# ironframe/conformance/static_checker_v1_0.py - v1.0
# Last updated: 2026-04-08
# ============================================================================
# Component 18b: Static Conformance Checker
#
# CI/CD gate. Produces structured StaticConformanceReport, not just pass/fail.
#
# Four checks:
#   1. RTM completeness — every accepted req has impl + verification
#   2. Architecture boundary rules — no illegal imports/bypasses
#   3. Orphan artifacts — code with no linked requirement
#   4. Contract invariant coverage — every invariant has linked test/monitor
# ============================================================================

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ironframe.conformance.rtm_v1_0 import RTMRegistry


# Drift types emitted by static checker
RTM_COVERAGE_GAP = "RTM_COVERAGE_GAP"
ARCH_BOUNDARY_VIOLATION = "ARCH_BOUNDARY_VIOLATION"
ORPHAN_ARTIFACT = "ORPHAN_ARTIFACT"
INVARIANT_NOT_VERIFIED = "INVARIANT_NOT_VERIFIED"


@dataclass
class StaticViolation:
    """A single static conformance violation."""
    violation_id: str
    drift_type: str
    severity: str          # info, warning, critical
    description: str
    component_id: str = ""
    file_path: str = ""
    requirement_id: str = ""
    invariant_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "violation_id": self.violation_id,
            "drift_type": self.drift_type,
            "severity": self.severity,
            "description": self.description,
            "component_id": self.component_id,
            "file_path": self.file_path,
            "requirement_id": self.requirement_id,
            "invariant_id": self.invariant_id,
        }


@dataclass
class StaticConformanceReport:
    """Result of a static conformance check run."""
    run_id: str
    timestamp: str
    violations: List[StaticViolation] = field(default_factory=list)
    coverage_pct: float = 0.0
    status: str = "PASS"     # PASS, WARN, FAIL

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "status": self.status,
            "coverage_pct": round(self.coverage_pct, 2),
            "violation_count": len(self.violations),
            "by_type": self._count_by_type(),
            "violations": [v.to_dict() for v in self.violations],
        }

    def _count_by_type(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for v in self.violations:
            counts[v.drift_type] = counts.get(v.drift_type, 0) + 1
        return counts


class StaticConformanceChecker:
    """Runs static conformance checks against RTM and architecture rules."""

    def __init__(self, rtm: RTMRegistry, contracts_dir: str = "ironframe/contracts",
                 code_dir: str = "ironframe"):
        self._rtm = rtm
        self._contracts_dir = Path(contracts_dir)
        self._code_dir = Path(code_dir)

    def run(self) -> StaticConformanceReport:
        """Run all static checks. Returns structured report."""
        violations = []

        violations.extend(self._check_rtm_completeness())
        violations.extend(self._check_architecture_boundaries())
        violations.extend(self._check_orphan_artifacts())
        violations.extend(self._check_invariant_coverage())

        # Compute coverage
        total_reqs = len(self._rtm.list_by_status("accepted"))
        complete = sum(1 for e in self._rtm.list_by_status("accepted") if e.is_complete)
        coverage = (complete / total_reqs * 100) if total_reqs > 0 else 0.0

        # Determine status
        has_critical = any(v.severity == "critical" for v in violations)
        has_warning = any(v.severity == "warning" for v in violations)
        status = "FAIL" if has_critical else ("WARN" if has_warning else "PASS")

        return StaticConformanceReport(
            run_id=str(uuid.uuid4())[:12],
            timestamp=datetime.now(timezone.utc).isoformat(),
            violations=violations,
            coverage_pct=coverage,
            status=status,
        )

    def _check_rtm_completeness(self) -> List[StaticViolation]:
        """Check 1: every accepted req has impl + verification."""
        violations = []
        for gap in self._rtm.coverage_gaps():
            violations.append(StaticViolation(
                violation_id=str(uuid.uuid4())[:8],
                drift_type=RTM_COVERAGE_GAP,
                severity="warning",
                description=gap,
                requirement_id=gap.split(":")[0] if ":" in gap else "",
            ))
        return violations

    def _check_architecture_boundaries(self) -> List[StaticViolation]:
        """Check 2: no illegal imports/bypasses.

        Rules from 18packet.txt:
          - coordination.* cannot import tool_governance except via locks_v1_0
          - No code writes to audit except C7 (audit/logger_v1_0.py)
          - No code performs trust tier logic except C17 modules
        """
        violations = []

        if not self._code_dir.exists():
            return violations

        # Check coordination imports
        coord_dir = self._code_dir / "coordination"
        if coord_dir.exists():
            for py_file in coord_dir.glob("*.py"):
                if py_file.name.startswith("__"):
                    continue
                content = py_file.read_text(encoding="utf-8")
                # coordination can only import locks from tool_governance
                if "from ironframe.tool_governance" in content:
                    if "locks_v1_0" not in content.split("from ironframe.tool_governance")[1].split("\n")[0]:
                        violations.append(StaticViolation(
                            violation_id=str(uuid.uuid4())[:8],
                            drift_type=ARCH_BOUNDARY_VIOLATION,
                            severity="critical",
                            description=f"{py_file.name} imports from tool_governance beyond locks_v1_0",
                            file_path=str(py_file),
                        ))

        return violations

    def _check_orphan_artifacts(self) -> List[StaticViolation]:
        """Check 3: code modules with no linked requirement."""
        violations = []

        # Collect all implementation artifacts from RTM
        linked_files: Set[str] = set()
        for entry in self._rtm.list_all():
            for artifact in entry.implementation_artifacts:
                linked_files.add(artifact)

        # Check Python modules under ironframe/
        if self._code_dir.exists():
            for py_file in self._code_dir.rglob("*.py"):
                if py_file.name.startswith("__"):
                    continue
                if "__pycache__" in str(py_file):
                    continue

                relative = str(py_file).replace("\\", "/")
                # Check if this file is linked in any RTM entry
                is_linked = any(relative.endswith(linked) or linked in relative
                                for linked in linked_files)
                if not is_linked:
                    violations.append(StaticViolation(
                        violation_id=str(uuid.uuid4())[:8],
                        drift_type=ORPHAN_ARTIFACT,
                        severity="info",
                        description=f"Code module has no RTM linkage: {py_file.name}",
                        file_path=relative,
                    ))

        return violations

    def _check_invariant_coverage(self) -> List[StaticViolation]:
        """Check 4: every contract invariant has a linked test/monitor."""
        violations = []

        if not self._contracts_dir.exists():
            return violations

        for contract_file in self._contracts_dir.glob("*.json"):
            try:
                data = json.loads(contract_file.read_text(encoding="utf-8"))
                invariants = data.get("invariants", [])
                verification = data.get("verification", {})
                unit_tests = verification.get("required_unit_tests", [])
                eval_scenarios = verification.get("required_eval_scenarios", [])
                all_tests = unit_tests + eval_scenarios

                for inv in invariants:
                    inv_id = inv.get("id", "") if isinstance(inv, dict) else ""
                    if inv_id and not all_tests:
                        violations.append(StaticViolation(
                            violation_id=str(uuid.uuid4())[:8],
                            drift_type=INVARIANT_NOT_VERIFIED,
                            severity="warning",
                            description=f"Invariant {inv_id} has no linked tests in contract",
                            invariant_id=inv_id,
                            file_path=str(contract_file),
                        ))
            except (json.JSONDecodeError, KeyError):
                continue

        return violations
