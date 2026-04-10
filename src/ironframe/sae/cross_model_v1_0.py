# ============================================================================
# ironframe/sae/cross_model_v1_0.py - v1.0
# Last updated: 2026-04-04
# ============================================================================
# Cross-model verification using a DIFFERENT model family.
#
# CriticMode correction: NOT same-family debate. Uses Perplexity (web-grounded,
# different training data) to verify Claude output. Avoids the NeurIPS finding
# that same-family models converge on shared errors.
#
# This is Brian's proven scimode pattern generalized:
#   Claude generates -> Perplexity (with web access) checks -> structured verdict
#
# Returns per-claim: CONFIRMED / CONTRADICTED / INSUFFICIENT_EVIDENCE
# Logs both original output and cross-check to audit.
#
# Usage:
#   from ironframe.sae.cross_model_v1_0 import CrossModelVerifier
#   from ironframe.mal import get_client
#
#   client = get_client()
#   verifier = CrossModelVerifier(client)
#   verdict = verifier.verify(
#       claims=['Inflation peaked at 9.1% in June 2022'],
#       original_context='Economic analysis of 2022',
#   )
#   print(verdict)
#   # {'claims': [{'text': '...', 'status': 'CONFIRMED', 'evidence': '...'}], ...}
# ============================================================================

import json
from typing import Any, Dict, List, Optional

_VERIFY_SYSTEM_PROMPT = """You are a fact-checking verification system. Your job is to check claims made by another AI against your own knowledge and any available evidence.

For each claim provided, assess:
- CONFIRMED: You can independently verify this claim is accurate
- CONTRADICTED: You have evidence this claim is wrong (cite the correction)
- INSUFFICIENT_EVIDENCE: You cannot confirm or deny this claim

Be specific. If contradicted, state what the correct information is.
If confirmed, briefly note your basis.

Respond in this exact JSON format (no markdown, no code fences):
{
  "claims": [
    {
      "text": "the original claim",
      "status": "CONFIRMED/CONTRADICTED/INSUFFICIENT_EVIDENCE",
      "evidence": "your basis or correction",
      "confidence": 0.0-1.0
    }
  ],
  "overall_reliable": true/false,
  "summary": "one-line overall assessment"
}

Set overall_reliable=true only if no claims are CONTRADICTED."""


class CrossModelVerifier:
    """Cross-model verification using a different model family.

    Default preference is 'verification' which routes to Perplexity/Sonar
    (web-grounded, different training data than Claude).

    If the verification provider is not configured, falls back to 'fast'
    (same-family but still useful as a second opinion with different temp).
    """

    def __init__(self, client, preference: str = "verification"):
        self._client = client
        self._preference = preference

    def verify(
        self,
        claims: List[str],
        original_context: str = "",
        max_tokens: int = 1024,
    ) -> Dict[str, Any]:
        """Verify a list of claims using a different model family.

        Returns structured verdict with per-claim status.
        """
        claims_text = "\n".join(f"- {claim}" for claim in claims)

        user_prompt = "CLAIMS TO VERIFY:\n" + claims_text
        if original_context:
            user_prompt += f"\n\nORIGINAL CONTEXT:\n{original_context}"

        try:
            result = self._client.complete(
                prompt=user_prompt,
                system=_VERIFY_SYSTEM_PROMPT,
                preference=self._preference,
                max_tokens=max_tokens,
                temperature=0.0,
            )
        except Exception as exc:
            # Any failure (adapter missing, quota exhausted, network error)
            # degrades gracefully rather than crashing the verification pipeline
            return {
                "claims": [{"text": c, "status": "INSUFFICIENT_EVIDENCE",
                            "evidence": f"Verification unavailable: {type(exc).__name__}",
                            "confidence": 0.0} for c in claims],
                "overall_reliable": False,
                "summary": f"Cross-model verification failed: {type(exc).__name__}: {str(exc)[:100]}",
                "model_used": "",
                "cost_usd": 0.0,
                "degraded": True,
            }

        raw_text = result.get("text", "")
        verdict = self._parse_verdict(raw_text, claims)
        verdict["model_used"] = result.get("model", "")
        verdict["cost_usd"] = result.get("cost_usd", 0.0)
        verdict["degraded"] = False
        return verdict

    def extract_claims(
        self,
        text: str,
        max_tokens: int = 512,
    ) -> List[str]:
        """Extract verifiable factual claims from text using the primary model.

        Helper for when caller has full text rather than pre-extracted claims.
        Uses 'fast' preference since this is just extraction, not verification.
        """
        result = self._client.complete(
            prompt=f"Extract all verifiable factual claims from this text. "
                   f"Return one claim per line, no numbering, no bullets.\n\n{text}",
            system="Extract factual claims only. Skip opinions, hedged statements, "
                   "and subjective assessments. One claim per line.",
            preference="fast",
            max_tokens=max_tokens,
            temperature=0.0,
        )

        raw = result.get("text", "")
        claims = [line.strip().lstrip("- ").lstrip("* ")
                  for line in raw.strip().splitlines()
                  if line.strip()]
        return claims

    def verify_text(
        self,
        text: str,
        original_context: str = "",
        max_tokens: int = 1024,
    ) -> Dict[str, Any]:
        """End-to-end: extract claims from text, then verify each one.

        Convenience method that combines extract_claims + verify.
        """
        claims = self.extract_claims(text)
        if not claims:
            return {
                "claims": [],
                "overall_reliable": True,
                "summary": "No verifiable claims found in text",
                "model_used": "",
                "cost_usd": 0.0,
                "degraded": False,
            }
        return self.verify(claims, original_context, max_tokens)

    def _parse_verdict(self, text: str, original_claims: List[str]) -> Dict[str, Any]:
        """Parse verification response into structured verdict."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        try:
            parsed = json.loads(cleaned)
            return {
                "claims": parsed.get("claims", []),
                "overall_reliable": bool(parsed.get("overall_reliable", False)),
                "summary": parsed.get("summary", ""),
            }
        except (json.JSONDecodeError, KeyError):
            # Graceful degradation on parse failure
            return {
                "claims": [{"text": c, "status": "INSUFFICIENT_EVIDENCE",
                            "evidence": "Verification response parse error",
                            "confidence": 0.0} for c in original_claims],
                "overall_reliable": False,
                "summary": f"Parse error. Raw: {text[:200]}",
                "raw_response": text,
            }
