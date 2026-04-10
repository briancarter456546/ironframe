# ============================================================================
# ironframe/context/skill_tier_v1_0.py - v1.0
# Last updated: 2026-04-06
# ============================================================================
# Component 9f: Skill Tiering Integration
#
# Only 'core' tier loads into CONTRACT zone by default. Other tiers
# (examples, background, templates, references) go to RETRIEVED_CONTEXT
# on demand. A skill dumping its full body into CONTRACT = budget violation.
# ============================================================================

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Skill content tiers — only CORE goes to CONTRACT zone
CORE = "core"
EXAMPLES = "examples"
BACKGROUND = "background"
TEMPLATES = "templates"
REFERENCES = "references"

SKILL_TIERS = [CORE, EXAMPLES, BACKGROUND, TEMPLATES, REFERENCES]


@dataclass
class SkillContent:
    """Parsed skill content split by tier."""
    skill_name: str
    tiers: Dict[str, str] = field(default_factory=dict)  # tier -> content text

    @property
    def core_content(self) -> str:
        return self.tiers.get(CORE, "")

    @property
    def non_core_tiers(self) -> Dict[str, str]:
        return {k: v for k, v in self.tiers.items() if k != CORE and v.strip()}


def extract_core_tier(skill_text: str) -> str:
    """Extract the core tier from a skill body.

    v1: simple heuristic — everything before the first '## Examples',
    '## Background', '## Templates', or '## References' heading.
    If no tier headings found, the entire body is treated as core.
    """
    import re
    tier_pattern = re.compile(
        r"^##\s+(examples|background|templates|references)\b",
        re.IGNORECASE | re.MULTILINE,
    )
    match = tier_pattern.search(skill_text)
    if match:
        return skill_text[:match.start()].strip()
    return skill_text.strip()


def split_skill_tiers(skill_name: str, skill_text: str) -> SkillContent:
    """Split skill body into tiers based on section headings.

    v1: uses '## Tier_Name' headings. If no headings, everything is core.
    """
    import re

    result = SkillContent(skill_name=skill_name)
    tier_pattern = re.compile(
        r"^##\s+(examples|background|templates|references)\b",
        re.IGNORECASE | re.MULTILINE,
    )

    # Find all tier boundaries
    matches = list(tier_pattern.finditer(skill_text))

    if not matches:
        result.tiers[CORE] = skill_text.strip()
        return result

    # Everything before first tier heading = core
    result.tiers[CORE] = skill_text[:matches[0].start()].strip()

    # Each subsequent section
    for i, match in enumerate(matches):
        tier_name = match.group(1).lower()
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(skill_text)
        result.tiers[tier_name] = skill_text[start:end].strip()

    return result
