# ============================================================================
# ironframe/skills/registry_v1_0.py - v1.0
# Last updated: 2026-04-04
# ============================================================================
# Skill Registry -- catalog, versioning, dependency resolution.
#
# Scans skill directories for skill.md files, parses YAML frontmatter,
# validates required fields. Provides list/get/validate/activate interface.
#
# Reuses _parse_yaml_frontmatter from phase_v1_0.py (same parsing logic).
#
# Usage:
#   from ironframe.skills.registry_v1_0 import SkillRegistry
#   registry = SkillRegistry('.claude/skills')
#   registry.scan()
#   print(registry.list())
#   skill = registry.get('backtest-explore')
#   issues = registry.validate('backtest-explore')
# ============================================================================

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ironframe.state.phase_v1_0 import _parse_yaml_frontmatter


@dataclass
class SkillDefinition:
    """Parsed skill definition from a skill.md file."""
    name: str
    description: str = ""
    user_invocable: bool = False
    version: str = "1.0"
    tier: str = "domain"         # core, domain, protocol
    requires: List[str] = field(default_factory=list)  # skill dependencies
    phases: List[Dict[str, Any]] = field(default_factory=list)
    path: str = ""               # path to skill.md
    raw_frontmatter: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_frontmatter(cls, frontmatter: Dict[str, Any], path: str = "") -> "SkillDefinition":
        """Create from parsed YAML frontmatter dict."""
        requires = frontmatter.get("requires", [])
        if isinstance(requires, str):
            requires = [requires]

        phases = frontmatter.get("phases", [])
        if not isinstance(phases, list):
            phases = []

        return cls(
            name=frontmatter.get("name", ""),
            description=frontmatter.get("description", ""),
            user_invocable=bool(frontmatter.get("user_invocable", False)),
            version=str(frontmatter.get("version", "1.0")),
            tier=frontmatter.get("tier", "domain"),
            requires=requires,
            phases=phases,
            path=path,
            raw_frontmatter=frontmatter,
        )


class SkillRegistry:
    """Catalog of all available skills with validation and dependency resolution.

    Scans one or more skill directories for skill.md files.
    Thread-safe for reads after scan().
    """

    def __init__(self, *skill_dirs: str):
        self._dirs = [Path(d) for d in skill_dirs] if skill_dirs else [Path(".claude/skills")]
        self._skills: Dict[str, SkillDefinition] = {}

    def scan(self) -> int:
        """Scan all skill directories and load definitions.

        Returns count of skills found.
        """
        self._skills.clear()
        for skill_dir in self._dirs:
            if not skill_dir.exists():
                continue
            for skill_md in skill_dir.rglob("skill.md"):
                try:
                    text = skill_md.read_text(encoding="utf-8")
                    frontmatter = _parse_yaml_frontmatter(text)
                    if not frontmatter.get("name"):
                        # Derive name from parent directory
                        frontmatter["name"] = skill_md.parent.name

                    skill = SkillDefinition.from_frontmatter(frontmatter, str(skill_md))
                    if skill.name:
                        self._skills[skill.name] = skill
                except Exception:
                    continue
        return len(self._skills)

    def list(self, tier: Optional[str] = None, invocable_only: bool = False) -> List[str]:
        """List all skill names, optionally filtered."""
        results = []
        for name, skill in sorted(self._skills.items()):
            if tier and skill.tier != tier:
                continue
            if invocable_only and not skill.user_invocable:
                continue
            results.append(name)
        return results

    def get(self, name: str) -> Optional[SkillDefinition]:
        """Get a skill definition by name."""
        return self._skills.get(name)

    def validate(self, name: str) -> List[str]:
        """Validate a skill definition. Returns list of issues (empty = valid)."""
        skill = self._skills.get(name)
        if not skill:
            return [f"Skill '{name}' not found in registry"]

        issues = []

        if not skill.name:
            issues.append("Missing 'name' field")
        if not skill.description:
            issues.append("Missing 'description' field")

        # Check dependencies exist
        for dep in skill.requires:
            if dep not in self._skills:
                issues.append(f"Dependency '{dep}' not found in registry")

        # Check for circular dependencies
        if self._has_circular_deps(name, set()):
            issues.append("Circular dependency detected")

        return issues

    def resolve_dependencies(self, name: str) -> List[str]:
        """Return ordered list of skills that must be loaded before this one.

        Topological sort of dependency graph. Raises ValueError on circular deps.
        """
        visited = set()
        order = []
        self._topo_visit(name, visited, order, set())
        # Remove the skill itself from the list (it's the last item)
        return [s for s in order if s != name]

    def _topo_visit(self, name: str, visited: set, order: list, in_stack: set) -> None:
        """Recursive topological sort helper."""
        if name in in_stack:
            raise ValueError(f"Circular dependency detected involving '{name}'")
        if name in visited:
            return

        in_stack.add(name)
        skill = self._skills.get(name)
        if skill:
            for dep in skill.requires:
                self._topo_visit(dep, visited, order, in_stack)

        in_stack.discard(name)
        visited.add(name)
        order.append(name)

    def _has_circular_deps(self, name: str, visited: set) -> bool:
        """Check for circular dependencies."""
        try:
            self.resolve_dependencies(name)
            return False
        except ValueError:
            return True

    def summary(self) -> Dict[str, Any]:
        """Return registry summary."""
        by_tier = {}
        for skill in self._skills.values():
            by_tier.setdefault(skill.tier, []).append(skill.name)
        return {
            "total": len(self._skills),
            "by_tier": by_tier,
            "invocable": len([s for s in self._skills.values() if s.user_invocable]),
        }
