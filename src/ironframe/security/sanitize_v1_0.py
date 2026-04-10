# ============================================================================
# ironframe/security/sanitize_v1_0.py - v1.0
# Last updated: 2026-04-05
# ============================================================================
# Component 11d: Content Sanitization
#
# Sanitization rules by trust tier:
#   SYSTEM/OPERATOR: pass through
#   USER: strip instruction markup, preserve content meaning
#   EXTERNAL: strip all markup + role-switching, wrap in delimiters
#   HOSTILE: replace entirely, original preserved only in audit (hashed)
#
# Original content is ALWAYS preserved in the audit trail by hash.
# ============================================================================

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

from ironframe.security.trust_v1_0 import TrustTier


@dataclass
class SanitizedOutput:
    """Result of sanitizing content."""
    sanitized: str            # cleaned version (goes to model)
    original_hash: str        # SHA-256 of original (for audit)
    original_preserved: bool  # True if original kept for audit
    strips_applied: List[str] # what was removed/modified
    tier: str                 # trust tier name

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_hash": self.original_hash,
            "original_preserved": self.original_preserved,
            "strips_applied": self.strips_applied,
            "tier": self.tier,
            "sanitized_length": len(self.sanitized),
        }


# Patterns to strip from USER-tier content (instruction markup only)
_USER_STRIP_PATTERNS = [
    (r"<\|im_start\|>.*?<\|im_end\|>", "chatml_block"),
    (r"<\|im_start\|>|<\|im_end\|>|<\|system\|>|<\|user\|>|<\|assistant\|>", "chatml_delimiter"),
    (r"\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>", "llama_delimiter"),
]

# Patterns to strip from EXTERNAL-tier content (more aggressive)
_EXTERNAL_STRIP_PATTERNS = _USER_STRIP_PATTERNS + [
    (r"(?i)\b(ignore (all |your |previous )?instructions)\b", "instruction_override"),
    (r"(?i)\b(you are now|act as|pretend you are|from now on you)\b", "role_switch"),
    (r"(?i)\b(jailbreak|DAN|developer mode|admin mode|god mode)\b", "jailbreak_keyword"),
    (r"(?i)\bnew (system |)instructions?\s*:.*?(?:\n|$)", "injected_instruction"),
    (r"```system\b.*?```", "markdown_system_block"),
    (r"(?i)<\s*(system|assistant)\s*>.*?<\s*/\s*(system|assistant)\s*>", "xml_role_tag"),
]


def sanitize(content: str, tier: int) -> SanitizedOutput:
    """Sanitize content based on trust tier.

    Returns SanitizedOutput with the cleaned version and audit metadata.
    Original is always preserved by hash for the audit trail.
    """
    original_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    tier_name = TrustTier(tier).name
    strips = []

    # SYSTEM / OPERATOR: pass through
    if tier >= TrustTier.OPERATOR:
        return SanitizedOutput(
            sanitized=content,
            original_hash=original_hash,
            original_preserved=True,
            strips_applied=[],
            tier=tier_name,
        )

    # USER: strip instruction markup, preserve meaning
    if tier == TrustTier.USER:
        result = content
        for pattern, name in _USER_STRIP_PATTERNS:
            cleaned = re.sub(pattern, "", result)
            if cleaned != result:
                strips.append(name)
                result = cleaned
        result = result.strip()
        return SanitizedOutput(
            sanitized=result,
            original_hash=original_hash,
            original_preserved=True,
            strips_applied=strips,
            tier=tier_name,
        )

    # EXTERNAL: strip all markup + role-switching, wrap in delimiters
    if tier == TrustTier.EXTERNAL:
        result = content
        for pattern, name in _EXTERNAL_STRIP_PATTERNS:
            cleaned = re.sub(pattern, "", result, flags=re.DOTALL)
            if cleaned != result:
                strips.append(name)
                result = cleaned
        result = result.strip()
        # Wrap in explicit boundary markers
        result = f"[EXTERNAL_CONTENT_START]\n{result}\n[EXTERNAL_CONTENT_END]"
        strips.append("wrapped_in_delimiters")
        return SanitizedOutput(
            sanitized=result,
            original_hash=original_hash,
            original_preserved=True,
            strips_applied=strips,
            tier=tier_name,
        )

    # HOSTILE: replace entirely
    if tier <= TrustTier.HOSTILE:
        return SanitizedOutput(
            sanitized="[BLOCKED: hostile content detected]",
            original_hash=original_hash,
            original_preserved=True,  # preserved in audit by hash, not inline
            strips_applied=["full_content_blocked"],
            tier=tier_name,
        )

    # Fallback (should not reach)
    return SanitizedOutput(
        sanitized=content,
        original_hash=original_hash,
        original_preserved=True,
        strips_applied=[],
        tier=tier_name,
    )
