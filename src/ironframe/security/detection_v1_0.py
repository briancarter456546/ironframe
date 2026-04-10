# ============================================================================
# ironframe/security/detection_v1_0.py - v1.0
# Last updated: 2026-04-05
# ============================================================================
# Component 11b: Injection Pattern Detection
#
# Multi-signal detector for prompt injection attempts.
# v1: Lexical + structural only. Semantic deferred (needs embedding model).
#
# Patterns are HARDCODED in Python, not loaded from external file.
# This is a deliberate anti-injection measure — an external pattern file
# could itself be a target for injection (modify to whitelist attacks).
#
# Constitution: Law 3 (agents untrusted), RTM IF-REQ-008
# ============================================================================

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Threat levels
NONE = "none"
SUSPICIOUS = "suspicious"
DETECTED = "detected"
HOSTILE = "hostile"


@dataclass
class PatternRule:
    """A single detection rule."""
    rule_id: str
    category: str       # role_switch, instruction_override, delimiter_attack, encoding_evasion
    pattern: str         # regex pattern
    description: str
    severity: str        # "high", "critical"


@dataclass
class PatternMatch:
    """A single pattern match in content."""
    rule_id: str
    category: str
    match_text: str
    position: int
    severity: str


@dataclass
class ScanResult:
    """Result of scanning content for injection patterns."""
    clean: bool
    threat_level: str             # none, suspicious, detected, hostile
    matched_rules: List[PatternMatch] = field(default_factory=list)
    structural_flags: List[str] = field(default_factory=list)
    recommended_tier: str = ""    # may suggest downgrade to HOSTILE
    scan_duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clean": self.clean,
            "threat_level": self.threat_level,
            "matched_rules": [
                {"rule_id": m.rule_id, "category": m.category,
                 "match_text": m.match_text[:50], "severity": m.severity}
                for m in self.matched_rules
            ],
            "structural_flags": self.structural_flags,
            "recommended_tier": self.recommended_tier,
            "scan_duration_ms": round(self.scan_duration_ms, 2),
        }


# ============================================================================
# HARDCODED PATTERN RULES (anti-tamper: no external file loading)
# ============================================================================

_PATTERNS: List[PatternRule] = [
    # --- Role confusion ---
    PatternRule("RC-001", "role_switch",
                r"(?i)\b(you are now|act as if you|pretend you are|imagine you are)\b",
                "Role reassignment attempt", "high"),
    PatternRule("RC-002", "role_switch",
                r"(?i)\b(from now on you|your new (role|identity|persona) is)\b",
                "Persistent role override", "critical"),
    PatternRule("RC-003", "role_switch",
                r"(?i)\b(roleplay as|you('re| are) (a|an|the) (evil|unrestricted|unfiltered))\b",
                "Adversarial roleplay", "high"),

    # --- Instruction override ---
    PatternRule("IO-001", "instruction_override",
                r"(?i)\bignore\b.{0,20}\binstructions?\b",
                "Instruction override attempt", "critical"),
    PatternRule("IO-002", "instruction_override",
                r"(?i)\b(disregard|forget)\b.{0,20}\b(previous|prior|above|system|instructions?)\b",
                "Instruction dismissal", "critical"),
    PatternRule("IO-003", "instruction_override",
                r"(?i)\b(override|bypass|skip|disable) (safety|filter|restriction|guardrail|rule)\b",
                "Safety bypass attempt", "critical"),
    PatternRule("IO-004", "instruction_override",
                r"(?i)\b(jailbreak|DAN|developer mode|admin mode|god mode)\b",
                "Known jailbreak keyword", "critical"),
    PatternRule("IO-005", "instruction_override",
                r"(?i)\b(do not follow|stop being|break character|no longer bound)\b",
                "Character/constraint escape", "high"),
    PatternRule("IO-006", "instruction_override",
                r"(?i)\bnew (system |)instructions?\s*:",
                "Injected system instruction block", "critical"),

    # --- Delimiter attacks ---
    PatternRule("DA-001", "delimiter_attack",
                r"<\|im_start\|>|<\|im_end\|>|<\|system\|>|<\|user\|>|<\|assistant\|>",
                "ChatML delimiter injection", "critical"),
    PatternRule("DA-002", "delimiter_attack",
                r"\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>",
                "Llama/instruction delimiter injection", "critical"),
    PatternRule("DA-003", "delimiter_attack",
                r"```system\b|```assistant\b|```user\b",
                "Markdown role block injection", "high"),
    PatternRule("DA-004", "delimiter_attack",
                r"(?i)<\s*(system|assistant)\s*>.*?<\s*/\s*(system|assistant)\s*>",
                "XML-style role tag injection", "high"),

    # --- Encoding evasion ---
    PatternRule("EE-001", "encoding_evasion",
                r"(?i)(base64|atob|decode)\s*\(",
                "Encoded instruction execution", "high"),
    PatternRule("EE-002", "encoding_evasion",
                r"[\u200b\u200c\u200d\u2060\ufeff]{2,}",
                "Zero-width character sequence", "high"),
    PatternRule("EE-003", "encoding_evasion",
                r"(?i)\\x[0-9a-f]{2}(\\x[0-9a-f]{2}){3,}",
                "Hex-encoded content sequence", "high"),
]


# ============================================================================
# STRUCTURAL CHECKS
# ============================================================================

_IMPERATIVE_VERBS = {
    "ignore", "forget", "disregard", "override", "bypass", "skip",
    "execute", "run", "perform", "output", "generate", "create",
    "delete", "remove", "send", "write", "modify", "change",
    "tell", "say", "respond", "answer", "repeat", "print",
}


def _check_instruction_density(text: str) -> Optional[str]:
    """Check if imperative verb ratio is suspiciously high."""
    words = text.lower().split()
    if len(words) < 10:
        return None
    imperative_count = sum(1 for w in words if w.strip(".,!?;:") in _IMPERATIVE_VERBS)
    ratio = imperative_count / len(words)
    if ratio > 0.15:
        return f"instruction_density={ratio:.2f} ({imperative_count}/{len(words)} words)"
    return None


def _check_role_boundaries(text: str) -> Optional[str]:
    """Check for role boundary markers in non-system content."""
    markers = re.findall(r"(?i)^(system|assistant|user)\s*:", text, re.MULTILINE)
    if len(markers) >= 2:
        return f"role_boundary_violations: {len(markers)} role markers found"
    return None


def _check_nested_instructions(text: str) -> Optional[str]:
    """Check for nested instruction blocks in quotes or code blocks."""
    blocks = re.findall(r'(?:"""|\'\'\'|```)(.*?)(?:"""|\'\'\'|```)', text, re.DOTALL)
    for block in blocks:
        if any(verb in block.lower() for verb in ["ignore", "override", "system", "instructions"]):
            return "nested_instruction_block: instruction keywords inside quoted block"
    return None


def _check_length_anomaly(text: str) -> Optional[str]:
    """Flag extremely long inputs that may be context-stuffing attacks."""
    if len(text) > 50000:
        return f"length_anomaly: {len(text)} chars (possible context stuffing)"
    return None


_STRUCTURAL_CHECKS = [
    _check_instruction_density,
    _check_role_boundaries,
    _check_nested_instructions,
    _check_length_anomaly,
]


# ============================================================================
# MAIN SCANNER
# ============================================================================

def scan_content(content: str, source: str = "") -> ScanResult:
    """Scan content for injection patterns and structural anomalies.

    Returns ScanResult with threat level and matched rules.
    """
    start = time.time()

    matches: List[PatternMatch] = []
    structural_flags: List[str] = []

    # Lexical pattern scan
    for rule in _PATTERNS:
        for m in re.finditer(rule.pattern, content):
            matches.append(PatternMatch(
                rule_id=rule.rule_id,
                category=rule.category,
                match_text=m.group(0)[:80],
                position=m.start(),
                severity=rule.severity,
            ))

    # Structural checks
    for check_fn in _STRUCTURAL_CHECKS:
        flag = check_fn(content)
        if flag:
            structural_flags.append(flag)

    # Determine threat level
    has_critical = any(m.severity == "critical" for m in matches)
    has_high = any(m.severity == "high" for m in matches)
    has_structural = len(structural_flags) > 0

    if has_critical:
        threat_level = HOSTILE
        recommended_tier = "HOSTILE"
    elif has_high and has_structural:
        threat_level = DETECTED
        recommended_tier = "HOSTILE"
    elif has_high or (has_structural and len(structural_flags) >= 2):
        threat_level = SUSPICIOUS
        recommended_tier = ""  # keep original tier, but flag
    else:
        threat_level = NONE
        recommended_tier = ""

    elapsed = (time.time() - start) * 1000

    return ScanResult(
        clean=(threat_level == NONE),
        threat_level=threat_level,
        matched_rules=matches,
        structural_flags=structural_flags,
        recommended_tier=recommended_tier,
        scan_duration_ms=elapsed,
    )
