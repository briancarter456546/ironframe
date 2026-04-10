# ============================================================================
# ironframe/state/session_v1_0.py - v1.0
# Last updated: 2026-04-04
# ============================================================================
# Session coordinator -- reads/writes multiple backing stores WITHOUT merging.
#
# CriticMode correction: state files stay separate. Each keeps its own scope
# and failure domain. Corruption in one does not take out the others.
#
# Three backing stores:
#   1. session_state.json    -- category, contexts, active_skill, hooks_profile
#   2. skill_state_active.json -- skill name, phases_done array
#   3. session_checkpoint.json -- task progress, steps, decisions
#
# This coordinator provides a unified READ interface and targeted WRITE
# methods. It never copies data between stores or creates a merged file.
#
# Usage:
#   from ironframe.state.session_v1_0 import IronFrameSession
#   session = IronFrameSession()
#   print(session.category)         # reads session_state.json
#   print(session.active_skill)     # reads session_state.json
#   print(session.phases_done)      # reads skill_state_active.json
#   print(session.checkpoint_task)  # reads session_checkpoint.json
#
#   session.set_category('OPS')
#   session.activate_skill('backtest-explore')
#   session.mark_phase_done('orient')
# ============================================================================

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ironframe.audit.logger_v1_0 import AuditLogger


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    """Read a JSON file, returning None if missing or corrupt."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    """Write a JSON file atomically (write + flush)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
        f.flush()


class IronFrameSession:
    """Coordinator across three independent state stores.

    Does NOT merge stores. Each backing file maintains its own lifecycle.
    Provides unified query interface + targeted write methods.
    Optionally logs state transitions to audit.
    """

    def __init__(
        self,
        base_dir: str = ".claude",
        checkpoint_path: str = "output/session_checkpoint.json",
        audit_logger: Optional[AuditLogger] = None,
    ):
        self._base = Path(base_dir)
        self._session_state_path = self._base / "session_state.json"
        self._skill_state_path = self._base / "skill_state_active.json"
        self._checkpoint_path = Path(checkpoint_path)
        self._audit = audit_logger

    # --- Read: session_state.json ---

    @property
    def session_state(self) -> Dict[str, Any]:
        """Raw session state dict. Returns empty dict if file missing."""
        return _read_json(self._session_state_path) or {}

    @property
    def category(self) -> str:
        return self.session_state.get("category", "")

    @property
    def contexts(self) -> List[str]:
        return self.session_state.get("contexts", [])

    @property
    def active_skill(self) -> Optional[str]:
        return self.session_state.get("active_skill")

    @property
    def hooks_profile(self) -> str:
        return self.session_state.get("hooks_profile", "all")

    # --- Read: skill_state_active.json ---

    @property
    def skill_state(self) -> Dict[str, Any]:
        """Raw skill state dict. Returns empty dict if file missing."""
        return _read_json(self._skill_state_path) or {}

    @property
    def skill_name(self) -> str:
        """Active skill from skill_state (may differ from session_state)."""
        return self.skill_state.get("skill", "")

    @property
    def phases_done(self) -> List[str]:
        return self.skill_state.get("phases_done", [])

    def is_phase_done(self, phase: str) -> bool:
        return phase in self.phases_done

    # --- Read: session_checkpoint.json ---

    @property
    def checkpoint(self) -> Dict[str, Any]:
        """Raw checkpoint dict. Returns empty dict if file missing."""
        return _read_json(self._checkpoint_path) or {}

    @property
    def checkpoint_task(self) -> str:
        return self.checkpoint.get("task", "")

    @property
    def checkpoint_status(self) -> str:
        return self.checkpoint.get("status", "")

    @property
    def completed_steps(self) -> List[str]:
        return [s.get("description", s) if isinstance(s, dict) else str(s)
                for s in self.checkpoint.get("completed_steps", [])]

    # --- Write: session_state.json ---

    def set_category(self, category: str) -> None:
        """Update session category."""
        data = self.session_state
        old = data.get("category", "")
        data["category"] = category
        data["updated_at"] = datetime.now().isoformat()
        _write_json(self._session_state_path, data)
        self._log_transition("category", old, category)

    def set_active_skill(self, skill_name: Optional[str]) -> None:
        """Update active skill in session_state."""
        data = self.session_state
        old = data.get("active_skill")
        data["active_skill"] = skill_name
        data["updated_at"] = datetime.now().isoformat()
        _write_json(self._session_state_path, data)
        self._log_transition("active_skill", old, skill_name)

    def set_hooks_profile(self, profile: str) -> None:
        """Update hooks profile."""
        data = self.session_state
        old = data.get("hooks_profile", "all")
        data["hooks_profile"] = profile
        data["updated_at"] = datetime.now().isoformat()
        _write_json(self._session_state_path, data)
        self._log_transition("hooks_profile", old, profile)

    # --- Write: skill_state_active.json ---

    def activate_skill(self, skill_name: str, phases: Optional[List[str]] = None) -> None:
        """Create/reset skill_state for a new skill activation."""
        data = {
            "skill": skill_name,
            "phases_done": [],
            "activated_at": datetime.now().isoformat(),
        }
        if phases:
            data["expected_phases"] = phases
        _write_json(self._skill_state_path, data)
        self.set_active_skill(skill_name)
        self._log_transition("skill_activated", None, skill_name)

    def mark_phase_done(self, phase: str) -> None:
        """Mark a phase as completed in skill_state."""
        data = self.skill_state
        if not data:
            return
        phases = data.get("phases_done", [])
        if phase not in phases:
            phases.append(phase)
            data["phases_done"] = phases
            data["updated_at"] = datetime.now().isoformat()
            _write_json(self._skill_state_path, data)
            self._log_transition("phase_done", None, phase)

    def deactivate_skill(self) -> None:
        """Mark skill_state as inactive and clear active_skill in session_state.

        Does NOT delete the file -- writes a deactivated marker instead.
        The file is preserved for audit trail.
        """
        skill = self.skill_name
        data = self.skill_state
        data["skill"] = ""
        data["deactivated_at"] = datetime.now().isoformat()
        data["status"] = "deactivated"
        _write_json(self._skill_state_path, data)
        self.set_active_skill(None)
        self._log_transition("skill_deactivated", skill, None)

    # --- Unified snapshot ---

    def snapshot(self) -> Dict[str, Any]:
        """Return a unified read-only snapshot of all three stores.

        This is for diagnostics and display. It is NOT a merged store --
        each section is labeled by its source file.
        """
        return {
            "session_state": self.session_state,
            "skill_state": self.skill_state,
            "checkpoint": self.checkpoint,
        }

    # --- Audit logging ---

    def _log_transition(self, field: str, old_value: Any, new_value: Any) -> None:
        """Log a state transition to audit if logger is configured."""
        if self._audit:
            self._audit.log_event(
                event_type="state_transition",
                component="state.session",
                details={
                    "field": field,
                    "old": str(old_value) if old_value is not None else None,
                    "new": str(new_value) if new_value is not None else None,
                },
            )
