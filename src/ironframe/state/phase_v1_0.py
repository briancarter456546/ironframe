# ============================================================================
# ironframe/state/phase_v1_0.py - v1.0
# Last updated: 2026-04-04
# ============================================================================
# Generic phase gate enforcement from skill.md YAML frontmatter.
#
# Replaces hardcoded if/else per skill in skill-phase-gate.sh with a
# data-driven approach. Skills declare their phases in frontmatter:
#
#   ---
#   name: backtest-explore
#   phases:
#     - name: orient
#       required_before: [explore, test]
#     - name: explore
#       required_before: [test]
#     - name: test
#       required_before: [validate]
#     - name: validate
#       required_before: [record]
#     - name: record
#   ---
#
# Skills WITHOUT phase declarations: gate always passes (backward compat).
# Skills WITH declarations: enforced generically via dependency graph.
#
# Usage (Python):
#   from ironframe.state.phase_v1_0 import PhaseGate
#   gate = PhaseGate.from_skill_file('.claude/skills/backtest-explore/skill.md')
#   result = gate.check('test', phases_done=['orient', 'explore'])
#   # result.allowed = True
#   result = gate.check('test', phases_done=['orient'])
#   # result.allowed = False, result.missing = ['explore']
#
# Usage (CLI):
#   python -m ironframe.state.phase_v1_0 check --skill backtest-explore --phase test
#   (reads skill_state_active.json for phases_done)
# ============================================================================

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class PhaseDeclaration:
    """A single phase in a skill's lifecycle."""
    name: str
    required_before: List[str] = field(default_factory=list)


@dataclass
class GateResult:
    """Result of a phase gate check."""
    allowed: bool
    phase: str
    missing: List[str] = field(default_factory=list)
    message: str = ""


def _parse_yaml_frontmatter(text: str) -> Dict:
    """Minimal YAML frontmatter parser for skill.md files.

    Handles the subset we need: scalar values and simple lists.
    Does NOT require PyYAML -- pure stdlib.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}

    frontmatter_lines = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        frontmatter_lines.append(line)

    result = {}
    current_key = None
    current_list = None

    for line in frontmatter_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # List item under a key
        if stripped.startswith("- ") and current_key is not None:
            item = stripped[2:].strip()
            # Check if item is a dict (has "name:" etc)
            if ":" in item and not item.startswith("["):
                if current_list is None:
                    current_list = []
                # Parse inline key: value
                k, v = item.split(":", 1)
                k = k.strip()
                v = v.strip()
                # Check if this starts a new list-of-dicts item
                if not current_list or k in (current_list[-1] if current_list else {}):
                    current_list.append({})
                current_list[-1][k] = _parse_value(v)
            else:
                if current_list is None:
                    current_list = []
                current_list.append(_parse_value(item))
            result[current_key] = current_list
            continue

        # Nested key under a list item (indented with spaces)
        if line.startswith("      ") and current_key and current_list:
            stripped_inner = line.strip()
            if ":" in stripped_inner:
                k, v = stripped_inner.split(":", 1)
                k = k.strip()
                v = v.strip()
                if current_list:
                    current_list[-1][k] = _parse_value(v)
                result[current_key] = current_list
                continue

        # Top-level key: value
        if ":" in stripped:
            k, v = stripped.split(":", 1)
            k = k.strip()
            v = v.strip()
            current_key = k
            current_list = None
            if v:
                result[k] = _parse_value(v)
            # else: value will come as list items below

    return result


def _parse_value(v: str):
    """Parse a YAML scalar value."""
    if not v:
        return ""
    # Boolean
    if v.lower() in ("true", "yes"):
        return True
    if v.lower() in ("false", "no"):
        return False
    # Inline list [a, b, c]
    if v.startswith("[") and v.endswith("]"):
        items = v[1:-1].split(",")
        return [item.strip().strip("'\"") for item in items if item.strip()]
    # Quoted string
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    # Number
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return v


class PhaseGate:
    """Generic phase gate enforcer driven by skill.md frontmatter.

    Skills without phase declarations: gate always passes.
    Skills with declarations: checks dependency graph.
    """

    def __init__(self, skill_name: str, phases: Optional[List[PhaseDeclaration]] = None):
        self.skill_name = skill_name
        self.phases = phases or []
        self._phase_map: Dict[str, PhaseDeclaration] = {p.name: p for p in self.phases}

    @property
    def has_phases(self) -> bool:
        return len(self.phases) > 0

    @property
    def phase_names(self) -> List[str]:
        return [p.name for p in self.phases]

    def check(self, target_phase: str, phases_done: List[str]) -> GateResult:
        """Check if target_phase can proceed given phases_done.

        Returns GateResult with allowed=True if:
          - This gate has no phase declarations (backward compat)
          - target_phase is not in the declaration (unknown phase, allow)
          - All prerequisites for target_phase are in phases_done
        """
        if not self.has_phases:
            return GateResult(allowed=True, phase=target_phase, message="No phase declarations")

        if target_phase not in self._phase_map:
            return GateResult(allowed=True, phase=target_phase, message="Phase not declared, allowing")

        # Find which phases list this target as required_before
        # i.e., which phases must be done before target_phase
        prerequisites = []
        for phase in self.phases:
            if target_phase in phase.required_before:
                # This means `phase` blocks phases in required_before,
                # but that's the wrong direction. Let me re-read the spec.
                # "required_before: [explore, test]" on orient means
                # orient is required before explore and test.
                # So if target is "test", we need to find all phases where
                # target is in their required_before... no.
                # Actually: orient.required_before = [explore, test] means
                # orient must be done before explore and test.
                # So to enter "test", we need all phases P where "test" is
                # in P.required_before. That means P must be done.
                prerequisites.append(phase.name)

        missing = [p for p in prerequisites if p not in phases_done]

        if missing:
            return GateResult(
                allowed=False,
                phase=target_phase,
                missing=missing,
                message=f"Phase '{target_phase}' blocked: prerequisites not done: {missing}",
            )

        return GateResult(allowed=True, phase=target_phase)

    @classmethod
    def from_skill_file(cls, skill_path: str) -> "PhaseGate":
        """Load phase declarations from a skill.md file."""
        path = Path(skill_path)
        if not path.exists():
            return cls(skill_name=path.stem, phases=[])

        text = path.read_text(encoding="utf-8")
        frontmatter = _parse_yaml_frontmatter(text)
        skill_name = frontmatter.get("name", path.parent.name)

        raw_phases = frontmatter.get("phases", [])
        if not isinstance(raw_phases, list):
            return cls(skill_name=skill_name, phases=[])

        phases = []
        for item in raw_phases:
            if isinstance(item, dict):
                name = item.get("name", "")
                req = item.get("required_before", [])
                if isinstance(req, str):
                    req = [req]
                if name:
                    phases.append(PhaseDeclaration(name=name, required_before=req))

        return cls(skill_name=skill_name, phases=phases)

    @classmethod
    def from_skills_dir(cls, skills_dir: str = ".claude/skills") -> Dict[str, "PhaseGate"]:
        """Load all phase gates from a skills directory."""
        gates = {}
        base = Path(skills_dir)
        if not base.exists():
            return gates
        for skill_md in base.rglob("skill.md"):
            gate = cls.from_skill_file(str(skill_md))
            if gate.skill_name:
                gates[gate.skill_name] = gate
        return gates


# --- CLI interface ---

def _cli_check(args):
    """CLI: check if a phase is allowed."""
    import argparse
    parser = argparse.ArgumentParser(description="Check phase gate")
    parser.add_argument("--skill", required=True, help="Skill name")
    parser.add_argument("--phase", required=True, help="Target phase to check")
    parser.add_argument("--skills-dir", default=".claude/skills", help="Skills directory")
    parser.add_argument("--state-file", default=".claude/skill_state_active.json",
                        help="Skill state file")
    parsed = parser.parse_args(args)

    # Load gate
    skill_path = Path(parsed.skills_dir) / parsed.skill / "skill.md"
    gate = PhaseGate.from_skill_file(str(skill_path))

    if not gate.has_phases:
        print(json.dumps({"allowed": True, "reason": "no phase declarations"}))
        sys.exit(0)

    # Read phases_done from state file
    phases_done = []
    state_path = Path(parsed.state_file)
    if state_path.exists():
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            if state.get("skill") == parsed.skill:
                phases_done = state.get("phases_done", [])
        except (json.JSONDecodeError, OSError):
            pass

    result = gate.check(parsed.phase, phases_done)
    print(json.dumps({
        "allowed": result.allowed,
        "phase": result.phase,
        "missing": result.missing,
        "message": result.message,
    }))
    sys.exit(0 if result.allowed else 1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        _cli_check(sys.argv[2:])
    else:
        print("Usage: python -m ironframe.state.phase_v1_0 check --skill NAME --phase PHASE")
        sys.exit(1)
