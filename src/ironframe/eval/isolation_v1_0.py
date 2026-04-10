# ============================================================================
# ironframe/eval/isolation_v1_0.py - v1.0
# Last updated: 2026-04-07
# ============================================================================
# Component 13e: Eval Isolation
#
# Eval runs are isolated from production state:
#   - Eval-specific KB snapshot (copy, not live)
#   - Sandboxed tool stubs (no live credentials)
#   - Results to eval audit store (separate from production)
#   - Budget tracked separately
#
# Temp dirs use ironframe_eval_ prefix for visibility.
# Cleanup is caller's responsibility via standard temp dir management.
# ============================================================================

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from ironframe.audit.logger_v1_0 import AuditLogger


@dataclass
class EvalEnvironment:
    """Isolated environment for eval runs."""
    kb_snapshot_path: str = ""
    tool_stubs: Dict[str, Any] = field(default_factory=dict)
    audit_store_path: str = ""
    budget_cap_usd: float = 1.0
    temp_dir: str = ""
    _audit_logger: Optional[AuditLogger] = field(default=None, repr=False)

    @property
    def audit_logger(self) -> Optional[AuditLogger]:
        return self._audit_logger

    @property
    def is_temp(self) -> bool:
        """True if environment is in a temp directory."""
        return self.temp_dir.startswith(tempfile.gettempdir())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kb_snapshot_path": self.kb_snapshot_path,
            "audit_store_path": self.audit_store_path,
            "budget_cap_usd": self.budget_cap_usd,
            "temp_dir": self.temp_dir,
            "is_temp": self.is_temp,
        }


def create_eval_environment(
    production_kb_path: str = "",
    tool_stubs: Optional[Dict[str, Any]] = None,
    budget_cap_usd: float = 1.0,
) -> EvalEnvironment:
    """Create an isolated eval environment.

    Copies production KB to a temp location. Creates separate audit store.
    Temp dir uses ironframe_eval_ prefix for visibility in process monitors.

    Cleanup: temp dirs are managed by the OS temp cleanup policy.
    For manual cleanup: the temp_dir path is exposed on the returned object.
    """
    temp_dir = tempfile.mkdtemp(prefix="ironframe_eval_")

    # Snapshot KB if provided
    kb_snapshot = ""
    if production_kb_path and Path(production_kb_path).exists():
        kb_snapshot = str(Path(temp_dir) / "eval_kb.db")
        shutil.copy2(production_kb_path, kb_snapshot)

    # Separate audit store
    audit_path = str(Path(temp_dir) / "eval_audit")
    Path(audit_path).mkdir(exist_ok=True)
    audit_logger = AuditLogger(output_dir=audit_path, filename="eval_audit.jsonl")

    return EvalEnvironment(
        kb_snapshot_path=kb_snapshot,
        tool_stubs=tool_stubs or {},
        audit_store_path=audit_path,
        budget_cap_usd=budget_cap_usd,
        temp_dir=temp_dir,
        _audit_logger=audit_logger,
    )
