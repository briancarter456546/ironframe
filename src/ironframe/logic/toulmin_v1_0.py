# ============================================================================
# ironframe/logic/toulmin_v1_0.py - v1.0
# Last updated: 2026-04-05
# ============================================================================
# Toulmin argument schema + validation.
#
# Six components per argument:
#   CLAIM    - the assertion being made
#   GROUNDS  - evidence supporting the claim
#   WARRANT  - WHY the grounds support the claim (the logical bridge)
#   BACKING  - what supports the warrant itself
#   QUALIFIER - confidence level and scope limits
#   REBUTTAL  - strongest counterargument acknowledged
#
# Dual use:
#   1. SAE Tier 0: generate a prompt addendum that forces structured reasoning
#   2. Validation: check if a completed argument has all required components
#
# Usage:
#   from ironframe.logic.toulmin_v1_0 import ToulminArgument, toulmin_prompt
#
#   # Build and validate an argument
#   arg = ToulminArgument(
#       claim="RSI2 < 10 is a profitable entry signal",
#       grounds=["PF = 3.56 over 258 trades", "Win rate 81.4%"],
#       warrant="Extreme oversold readings revert to mean within 5 days",
#       backing="Mean reversion is well-documented in equity markets",
#       qualifier="On SPY with SMA200 filter, 2015-2025 data",
#       rebuttal="May fail in sustained bear markets (VIX > 35)",
#   )
#   issues = arg.validate()
#   print(arg.format())
#
#   # Get prompt addendum for SAE Tier 0
#   print(toulmin_prompt())
# ============================================================================

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ToulminArgument:
    """A structured argument following Toulmin's model."""

    claim: str = ""
    grounds: List[str] = field(default_factory=list)
    warrant: str = ""
    backing: str = ""
    qualifier: str = ""
    rebuttal: str = ""

    def validate(self) -> List[str]:
        """Check completeness. Returns list of issues (empty = valid).

        Required: claim, at least one ground, warrant.
        Recommended: qualifier, rebuttal.
        Optional: backing.
        """
        issues = []

        if not self.claim.strip():
            issues.append("Missing CLAIM: no assertion stated")
        if not self.grounds:
            issues.append("Missing GROUNDS: no evidence provided")
        elif all(not g.strip() for g in self.grounds):
            issues.append("Empty GROUNDS: evidence items are blank")
        if not self.warrant.strip():
            issues.append("Missing WARRANT: no explanation of WHY grounds support claim")
        if not self.qualifier.strip():
            issues.append("Missing QUALIFIER: no confidence level or scope limits stated")
        if not self.rebuttal.strip():
            issues.append("Missing REBUTTAL: no counterargument acknowledged")

        return issues

    @property
    def is_complete(self) -> bool:
        """True if all required + recommended fields are populated."""
        return len(self.validate()) == 0

    @property
    def strength(self) -> str:
        """Quick assessment of argument completeness."""
        issues = self.validate()
        if len(issues) == 0:
            return "STRONG"
        elif len(issues) <= 2 and all("Missing QUALIFIER" in i or "Missing REBUTTAL" in i
                                       for i in issues):
            return "ADEQUATE"
        else:
            return "WEAK"

    def format(self) -> str:
        """Format as readable text block."""
        lines = []
        lines.append(f"CLAIM: {self.claim}")
        lines.append(f"GROUNDS:")
        for i, g in enumerate(self.grounds, 1):
            lines.append(f"  {i}. {g}")
        lines.append(f"WARRANT: {self.warrant}")
        if self.backing:
            lines.append(f"BACKING: {self.backing}")
        lines.append(f"QUALIFIER: {self.qualifier}")
        lines.append(f"REBUTTAL: {self.rebuttal}")
        lines.append(f"STRENGTH: {self.strength}")
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        return {
            "claim": self.claim,
            "grounds": self.grounds,
            "warrant": self.warrant,
            "backing": self.backing,
            "qualifier": self.qualifier,
            "rebuttal": self.rebuttal,
            "strength": self.strength,
            "issues": self.validate(),
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "ToulminArgument":
        return cls(
            claim=d.get("claim", ""),
            grounds=d.get("grounds", []),
            warrant=d.get("warrant", ""),
            backing=d.get("backing", ""),
            qualifier=d.get("qualifier", ""),
            rebuttal=d.get("rebuttal", ""),
        )


def toulmin_prompt() -> str:
    """Return a prompt addendum that forces Toulmin-structured reasoning.

    Inject this into the system prompt for SAE Tier 0 (free, no API call).
    """
    return """When analyzing claims or making recommendations, structure your reasoning using the Toulmin model:

1. CLAIM: State the assertion explicitly
2. GROUNDS: List the specific evidence supporting it
3. WARRANT: Explain WHY these grounds support this claim (the logical bridge)
4. QUALIFIER: State your confidence level and the scope/conditions where this holds
5. REBUTTAL: Name the strongest counterargument or exception
6. BACKING: What supports the warrant itself? (if the warrant isn't self-evident)

Do not skip the WARRANT -- it is the most important component. "The data shows X" is grounds, not a warrant. The warrant explains the mechanism: WHY does X being true make the claim likely?

Do not skip the REBUTTAL -- acknowledging the strongest counterargument is what separates a strong argument from a one-sided assertion."""


def toulmin_validation_prompt() -> str:
    """Return a prompt for validating an existing argument against Toulmin schema.

    Use as a follow-up check on completed analysis.
    """
    return """Review the argument above using the Toulmin model. For each component, assess:

1. CLAIM: Is there a clear, explicit assertion? Or is the conclusion buried/implicit?
2. GROUNDS: Is there specific evidence cited? Or just general assertions?
3. WARRANT: Is there an explicit explanation of WHY the evidence supports the claim? Or does it jump from evidence to conclusion?
4. QUALIFIER: Are confidence limits and scope conditions stated? Or is the claim presented as absolute?
5. REBUTTAL: Is the strongest counterargument addressed? Or are objections ignored?
6. BACKING: If the warrant is non-obvious, is it itself supported?

For each missing or weak component, state specifically what is missing and how it should be strengthened."""


def parse_toulmin_from_text(text: str) -> ToulminArgument:
    """Best-effort parse of a Toulmin-structured text block.

    Looks for labeled sections (CLAIM:, GROUNDS:, WARRANT:, etc.)
    Returns ToulminArgument with whatever was found.
    """
    arg = ToulminArgument()
    current_field = None
    grounds_buffer = []

    for line in text.splitlines():
        stripped = line.strip()
        upper = stripped.upper()

        if upper.startswith("CLAIM:"):
            current_field = "claim"
            arg.claim = stripped[6:].strip()
        elif upper.startswith("GROUNDS:"):
            current_field = "grounds"
            rest = stripped[8:].strip()
            if rest:
                grounds_buffer.append(rest)
        elif upper.startswith("WARRANT:"):
            current_field = "warrant"
            arg.warrant = stripped[8:].strip()
        elif upper.startswith("BACKING:"):
            current_field = "backing"
            arg.backing = stripped[8:].strip()
        elif upper.startswith("QUALIFIER:"):
            current_field = "qualifier"
            arg.qualifier = stripped[10:].strip()
        elif upper.startswith("REBUTTAL:"):
            current_field = "rebuttal"
            arg.rebuttal = stripped[9:].strip()
        elif current_field == "grounds" and stripped:
            # Continuation line for grounds (numbered or bulleted)
            item = stripped.lstrip("0123456789.-) ").strip()
            if item:
                grounds_buffer.append(item)
        elif current_field and stripped:
            # Continuation line for other fields
            existing = getattr(arg, current_field, "")
            if existing:
                setattr(arg, current_field, existing + " " + stripped)
            else:
                setattr(arg, current_field, stripped)

    arg.grounds = grounds_buffer
    return arg
